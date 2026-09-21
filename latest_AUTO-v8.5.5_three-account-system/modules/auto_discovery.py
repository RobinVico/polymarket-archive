"""AUTO 流水线 第2步: GLM 自动选品 (用户 2026-07-08 拍板)。

流程: 定时扫描完成后 → 挑出"有候选市场"的 tag 报告 → 逐个喂给智谱 GLM (联网搜索+深思考,
跟手动贴 Claude.ai 同一份 DISCOVERY prompt + cluster 字典, 外加"末尾必须输出 JSON 数组"指令)
→ 没有 JSON 就追问一条 (用户规则: 只追问一次) → 解析校验 → 存 auto_candidates 表。

🔒 本步不下单、不进测试仓、不碰钱 —— 只产出候选清单 (带 40~85 分流预演标签) 给用户检验
   GLM 选品水平 + 量真实成本。真买/进测试仓是第3/4步, 等用户点头。
🔑 key 隔离 (用户 2026-07-08 要求): 选品用 ZHIPUAI_API_KEY_DISCOVERY;
   重评用 ZHIPUAI_API_KEY_REEVAL (autobot.py 启动时映射给 auto_reeval 读的 ZHIPUAI_API_KEY)。
   两把 key 在智谱后台各自记账, 绝不混用。
"""
import os
import re
import json
import time
import threading
import logging
from datetime import datetime, timezone

log = logging.getLogger("auto_discovery")

# GLM 参数: 跟重评 v6.0.8 拉满配置同款, env AUTO_DISCOVERY_* 可覆盖
D_MODEL = os.environ.get("AUTO_DISCOVERY_GLM_MODEL", "glm-5.2")
D_MAX_TOKENS = int(os.environ.get("AUTO_DISCOVERY_GLM_MAX_TOKENS", "32000"))
D_REASONING = os.environ.get("AUTO_DISCOVERY_GLM_REASONING", "max")
D_SEARCH_COUNT = int(os.environ.get("AUTO_DISCOVERY_GLM_SEARCH_COUNT", "20"))
D_SEARCH_ENGINE = os.environ.get("AUTO_DISCOVERY_GLM_SEARCH_ENGINE", "search_pro")
D_TEMP = float(os.environ.get("AUTO_DISCOVERY_GLM_TEMP", "0.6"))

# 用户写死的分流线 (2026-07-08): 0.40 < 现价 < 0.85 → 真买; 否则 → 测试仓。恰好等于边界 → 测试仓。
ROUTE_REAL_MIN = 0.40
ROUTE_REAL_MAX = 0.85

# 用户规则 (2026-07-08, 已确认按"单个标签"算): 一个 tag 扫出的候选市场 < 5 个 → 该 tag 不送 GLM (省 API)。
# (边界 2026-07-08 用户二次确认: **≥5 就送**, 恰好 5 个也送。)
MIN_CANDIDATES = int(os.environ.get("AUTO_DISCOVERY_MIN_CANDIDATES", "5"))

# 用户 2026-07-08 拍板: 全自动链路改"扫一个喂一个, 多路并发" (每个 tag 丢 GLM 前当场重扫拿最新盘口,
# 排在后面的类别也不吃十几分钟前的旧数据)。并发数由 scratchpad 实测定: 该 discovery 账户重调用
# ~4 并发是可靠甜区, 更高会开始丢连接 (无 1302 硬墙, 是负载下甩连接; 生产 600s+重试能兜住)。
# env AUTO_DISCOVERY_CONCURRENCY 可调, 默认 4。
STREAM_CONCURRENCY = int(os.environ.get("AUTO_DISCOVERY_CONCURRENCY", "4"))

# 单 tag 硬超时熔断 (2026-07-20 用户拍板): GLM 一次调用挂死能冻结整条流水线 (实测 Iran 汇总调用挂了
# 2 小时, SDK 600s 超时没生效)。给每个 tag 的 GLM 处理套一堵墙钟硬墙: 超过这么多秒直接**踢掉本 tag**
# (卡死的子线程丢后台自生自灭, 不等它), 其余 tag 照常并发跑完。正常一个 tag 5~13 分钟, 默认 1200s(20min)
# 只砍真·卡死。env AUTO_DISCOVERY_TAG_TIMEOUT_S 可调; 设 0 关闭硬墙(退回老行为, 不建议)。
TAG_TIMEOUT_S = int(os.environ.get("AUTO_DISCOVERY_TAG_TIMEOUT_S", "1200"))

# 审查修复⑦ (2026-07-08): 选品并发锁 — 定时轮和手动 discover_now 撞上时只跑一个 (防重复烧 GLM)。
# RLock: run_for_slot 持锁后同线程再进 run_tag 不自锁。
_disc_lock = threading.RLock()

JSON_APPEND = """

---

# 🤖 机器读取要求 (最后必须输出 JSON)

以上分析照常写完后, **最末尾必须**输出一个 ```json 代码块: 内容是一个数组, 没有推荐就输出空数组 []。
每个推荐一个对象, 字段严格用这些名字 (跟上面推荐卡片一一对应):

```json
[{"slug": "market-slug", "title": "市场完整名", "side": "YES", "cur_price": 0.55, "q": 0.68, "confidence": "high", "stop_loss_tier": "event_driven", "end_date": "2026-08-31", "days_to_resolution": 54, "cluster_id": "topic-direction", "tag": "Iran", "reason": "一句话核心理由"}]
```

- side 只能 YES / NO; cur_price 和 q 用 0~1 小数; confidence 只能 high / medium / low;
  stop_loss_tier 只能 convergent / hybrid / event_driven。
- `q` = 你上面对该市场的**原始估算** (你真实判断的概率, 不做任何往市价的调整/收缩); `cur_price` = 你下注方向 token 的现价。
- JSON 块内不要注释、不要多余字段; 字符串里的英文引号必须转义。
"""

FOLLOWUP_MSG = ("上面的回复里没有找到合法的 ```json 代码块。现在请只输出那个 ```json 数组 "
                "(字段: slug/title/side/cur_price/q/confidence/stop_loss_tier/end_date/"
                "days_to_resolution/cluster_id/tag/reason), 不要任何其他文字。没有推荐就输出 []。")


def _key():
    return (os.environ.get("ZHIPUAI_API_KEY_DISCOVERY") or "").strip()


def is_configured():
    return bool(_key())


# ---------- DB (自建表, 不动同步来的 db.py) ----------

def _ensure_tables():
    from modules.db import get_conn
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS auto_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, scan_slot TEXT, tag TEXT,
        slug TEXT, title TEXT, side TEXT, cur_price REAL, q REAL, confidence TEXT,
        stop_loss_tier TEXT, end_date TEXT, days_to_resolution REAL, cluster_id TEXT,
        reason TEXT, route TEXT, raw_json TEXT, status TEXT DEFAULT 'new')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS auto_discovery_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, scan_slot TEXT, tag TEXT, started_at TEXT,
        ok INTEGER, n_recs INTEGER, n_invalid INTEGER, followup_used INTEGER,
        tokens_prompt INTEGER, tokens_completion INTEGER, error TEXT)""")
    conn.commit()
    conn.close()


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


# ---------- GLM 调用 ----------

def _glm_create_tolerant(client, **kwargs):
    """抄自 auto_reeval._glm_create (复制而非 import, 保证以后同步老项目代码时零耦合):
    SDK 不认某高级参数 (TypeError) 就按序去掉重试; 真 API 错误照抛。"""
    optional = ["extra_body", "thinking", "temperature", "max_tokens"]
    while True:
        try:
            return client.chat.completions.create(**kwargs)
        except TypeError:
            for k in optional:
                if k in kwargs:
                    log.warning(f"[discovery] GLM SDK 不认参数 {k}, 去掉重试")
                    kwargs.pop(k)
                    break
            else:
                raise


def _resp_text(resp):
    try:
        m = resp.choices[0].message
        t = (getattr(m, "content", None) or "")
        if not t.strip():
            t = (getattr(m, "reasoning_content", None) or "")
        return t
    except Exception:
        return ""


def _resp_usage(resp):
    try:
        u = getattr(resp, "usage", None)
        return int(getattr(u, "prompt_tokens", 0) or 0), int(getattr(u, "completion_tokens", 0) or 0)
    except Exception:
        return 0, 0


# ---------- 解析 ----------

def _extract_recs(text):
    """从回复里抠 ```json 块 → 推荐 dict 列表。返回 (recs, n_invalid, saw_valid_empty)。宽容: 数组/单对象都收。
    审查修复⑧ (2026-07-08):
    - saw_valid_empty=True 表示模型给了**合法空数组 []** (= 正经"无推荐") — 这种不该追问 (老代码会白追一次)。
    - 没有 ```json 围栏但整体就是裸 JSON (追问后模型常这么回) → 也收。"""
    recs, invalid = [], 0
    saw_valid_empty = False
    blocks = re.findall(r"```json\s*(.*?)```", text or "", re.DOTALL | re.IGNORECASE)
    if not blocks:
        t = (text or "").strip()
        if t.startswith("[") or t.startswith("{"):
            blocks = [t]
    for blk in blocks:
        try:
            data = json.loads(blk.strip())
        except Exception:
            invalid += 1
            continue
        if isinstance(data, list) and not data:
            saw_valid_empty = True
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict):
                invalid += 1
                continue
            r = _normalize(it)
            if r:
                recs.append(r)
            else:
                invalid += 1
    return recs, invalid, saw_valid_empty


def _normalize(it):
    """校验+归一化一条推荐; 不合格返回 None。"""
    try:
        slug = str(it.get("slug") or "").strip()
        side = str(it.get("side") or "").strip().upper()
        cur = it.get("cur_price")
        q = it.get("q")
        if not slug or side not in ("YES", "NO") or cur is None or q is None:
            return None
        cur = float(cur)
        q = float(q)
        if cur > 1:
            cur = cur / 100.0
        if q > 1:
            q = q / 100.0
        if not (0 < cur < 1) or not (0 < q < 1):
            return None
        # AUTO 用户拍板 (2026-07-18 起, 2026-07-20 收口): DISCOVERY prompt 里的"打五折"校准已**物理删除**,
        # GLM 直接给原始估算 q_raw; 校准统一挪到 Python 这里做一次 = 市场价 + 0.8×(q_raw − 市场价)。
        # GLM 原始 q 仍留在 raw_json 里可审计。(手动贴Claude流程没有这步 → 用原始, 见 CLAUDE.md 规则17)
        from modules.auto_calibrate import calibrate_q
        q = calibrate_q(q, cur)
        conf = str(it.get("confidence") or "").strip().lower()
        if conf not in ("high", "medium", "low"):
            conf = ""
        tier = str(it.get("stop_loss_tier") or "").strip().lower()
        if tier not in ("convergent", "hybrid", "event_driven"):
            tier = ""
        try:
            days = float(it.get("days_to_resolution"))
        except Exception:
            days = None
        return {
            "slug": slug, "title": str(it.get("title") or "")[:200], "side": side,
            "cur_price": cur, "q": q, "confidence": conf, "stop_loss_tier": tier,
            "end_date": str(it.get("end_date") or "")[:20], "days_to_resolution": days,
            "cluster_id": str(it.get("cluster_id") or "")[:80],
            "reason": str(it.get("reason") or "")[:500],
            "raw_json": json.dumps(it, ensure_ascii=False)[:2000],
        }
    except Exception:
        return None


def route_of(cur_price):
    """用户写死的分流规则: 0.40 < 现价 < 0.85 → real (真买); 否则 paper (测试仓)。"""
    try:
        p = float(cur_price)
    except Exception:
        return "paper"
    return "real" if (ROUTE_REAL_MIN < p < ROUTE_REAL_MAX) else "paper"


# ---------- prompt 组装 (对齐 dashboard /api/full_prompt, 但不依赖 Flask) ----------

def _build_prompt(tag_label):
    from modules.scanner import get_cached_report
    from modules.prompts import DISCOVERY_PROMPT
    report = get_cached_report(tag_label)
    if not report:
        return None
    try:
        from modules.clusters import get_cluster_dict_for_prompt
        cluster_md = get_cluster_dict_for_prompt() or ""
    except Exception as e:
        log.warning(f"[discovery] cluster 字典获取失败 (不影响): {e}")
        cluster_md = ""
    base = DISCOVERY_PROMPT.replace("{positions_list}", report)
    parts = [cluster_md, base, JSON_APPEND] if cluster_md else [base, JSON_APPEND]
    return "\n\n---\n\n".join(p for p in parts if p)


# ---------- 单 tag 跑一轮 ----------

def run_tag(tag_slug, tag_label, scan_slot):
    """一个 tag: 组 prompt → GLM → 无有效 JSON 追问一次 → 解析入库。返回 (n_recs, tokens_tuple)。"""
    from modules.db import get_conn
    # 审查修复⑦: 非阻塞抢锁 (手动单 tag 触发跟定时轮撞上 → 跳过, 不重复烧 GLM)
    if not _disc_lock.acquire(blocking=False):
        log.warning(f"[discovery] {tag_label}: 已有选品在跑, 本次触发跳过 (防重复调 GLM)")
        return 0, (0, 0)
    try:
        return _run_tag_locked(tag_slug, tag_label, scan_slot)
    finally:
        _disc_lock.release()


def _run_tag_locked(tag_slug, tag_label, scan_slot):
    from modules.db import get_conn
    started = _utcnow()
    n_recs = n_invalid = 0
    tp = tc = 0
    followup = 0
    err = None
    try:
        prompt = _build_prompt(tag_label)
        if not prompt:
            raise RuntimeError(f"tag '{tag_label}' 无缓存报告")
        from zhipuai import ZhipuAI
        try:
            client = ZhipuAI(api_key=_key(), timeout=600.0)
        except TypeError:
            client = ZhipuAI(api_key=_key())
        sysmsg = ("你是 Polymarket 选品分析师。先用 web_search 联网核实每个候选市场的最新一手信息, "
                  "按 prompt 里的方法论逐个分析, 最后除了推荐卡片, 还必须按要求输出 ```json 数组。")
        messages = [{"role": "system", "content": sysmsg},
                    {"role": "user", "content": prompt}]
        # 多轮自主搜索 agent (用户 2026-07-09 拍板: 像 Claude 一样搜→想→再搜)。失败自动回退老的一次性注入。
        text = None
        from modules.auto_glm_agent import AGENTIC_ON
        if AGENTIC_ON:
            try:
                from modules.auto_glm_agent import agentic_analyze
                sysmsg_agent = ("你是 Polymarket 选品分析师。你有一个可反复调用的 web_search 工具, "
                                "像研究员一样多轮使用: 先广撒网查各候选市场的最新动态, 对有苗头的再逐个深挖查证 "
                                "(一次一个查询词, 想查几次查几次, 有上限时会被提示)。查证充分后, "
                                "按 prompt 里的方法论输出完整分析, 最末尾必须按要求输出 ```json 数组。")
                _r = agentic_analyze(api_key=_key(), model=D_MODEL, system_msg=sysmsg_agent,
                                     user_prompt=prompt, max_tokens=D_MAX_TOKENS,
                                     temperature=D_TEMP, reasoning=D_REASONING,
                                     log_prefix=f"[discovery] {tag_label}")
                tp += _r["tp"]
                tc += _r["tc"]
                text = _r["text"]
                log.info(f"[discovery] {tag_label}: agent 自主搜索 {_r['n_searches']} 次完成")
            except Exception as _ae:
                log.warning(f"[discovery] {tag_label}: 多轮搜索 agent 失败 ({_ae}), 回退一次性注入搜索")
                text = None
        if text is None:
            tools = [{"type": "web_search", "web_search": {
                "enable": True, "search_engine": D_SEARCH_ENGINE,
                "search_query": (tag_label + " 最新新闻 news")[:78],
                "search_result": True, "count": D_SEARCH_COUNT, "content_size": "high",
            }}]
            resp = _glm_create_tolerant(
                client, model=D_MODEL, messages=messages, tools=tools,
                max_tokens=D_MAX_TOKENS, temperature=D_TEMP,
                thinking={"type": "enabled"},
                extra_body={"reasoning_effort": D_REASONING},
            )
            a, b = _resp_usage(resp)
            tp += a
            tc += b
            text = _resp_text(resp)
        recs, n_invalid, empty_ok = _extract_recs(text)
        if not recs and not empty_ok:
            # 用户规则 (2026-07-08 确认口径): "给的不对"就追问一次 — 覆盖 没JSON / JSON坏 / 字段全非法;
            # 模型明确给了合法空数组 [] = 正经"无推荐", 不追问 (省一次 API)。
            followup = 1
            log.info(f"[discovery] {tag_label}: 回复无有效 JSON (坏块 {n_invalid} 个), 追问一次")
            messages.append({"role": "assistant", "content": text[:60000]})
            messages.append({"role": "user", "content": FOLLOWUP_MSG})
            resp2 = _glm_create_tolerant(
                client, model=D_MODEL, messages=messages,
                max_tokens=8000, temperature=0.2,
                thinking={"type": "enabled"},
            )
            a, b = _resp_usage(resp2)
            tp += a
            tc += b
            recs, n_invalid, empty_ok = _extract_recs(_resp_text(resp2))
        # AUTO 2026-07-12: 从报告里收集带黑名单标记的 slug —— /auto 预演路由对它们显示"测试仓",
        # 跟 auto_trader 执行时的强制一致 (真买闸门永远关着)。真正的强制在 auto_trader, 这里只是预演展示。
        _bl_slugs = set()
        try:
            from modules.scanner import get_cached_report
            from modules.tags import BLACKLIST_REPORT_MARK
            for _ln in (get_cached_report(tag_label) or "").splitlines():
                if BLACKLIST_REPORT_MARK in _ln:
                    _mm = re.search(r"`([^`]+)`", _ln)
                    if _mm:
                        _bl_slugs.add(_mm.group(1))
        except Exception:
            pass
        conn = get_conn()
        for r in recs:
            dup = conn.execute(
                "SELECT 1 FROM auto_candidates WHERE scan_slot=? AND slug=? AND side=?",
                (scan_slot, r["slug"], r["side"])).fetchone()
            if dup:
                continue
            _prev_route = "paper" if r["slug"] in _bl_slugs else route_of(r["cur_price"])
            conn.execute(
                """INSERT INTO auto_candidates (created_at, scan_slot, tag, slug, title, side,
                   cur_price, q, confidence, stop_loss_tier, end_date, days_to_resolution,
                   cluster_id, reason, route, raw_json, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new')""",
                (_utcnow(), scan_slot, tag_label, r["slug"], r["title"], r["side"],
                 r["cur_price"], r["q"], r["confidence"], r["stop_loss_tier"], r["end_date"],
                 r["days_to_resolution"], r["cluster_id"], r["reason"],
                 _prev_route, r["raw_json"]))
            n_recs += 1
        conn.commit()
        conn.close()
        log.info(f"[discovery] {tag_label}: 入库 {n_recs} 条推荐 (无效 {n_invalid}, 追问 {followup}), tokens {tp}+{tc}")
    except Exception as e:
        err = str(e)[:500]
        log.exception(f"[discovery] {tag_label}: 失败")
    try:
        conn = get_conn()
        conn.execute(
            """INSERT INTO auto_discovery_runs (scan_slot, tag, started_at, ok, n_recs, n_invalid,
               followup_used, tokens_prompt, tokens_completion, error) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (scan_slot, tag_label, started, 0 if err else 1, n_recs, n_invalid, followup, tp, tc, err))
        conn.commit()
        conn.close()
    except Exception:
        log.exception("[discovery] run 记录写库失败")
    return n_recs, (tp, tc)


def _tags_with_candidates():
    """读 manifest, 返回 [(tag_slug, tag_label, n_candidates)] 只含有候选的 done tag。"""
    from modules.scanner import SCAN_MANIFEST, SCAN_REPORTS_DIR
    out = []
    try:
        with open(SCAN_MANIFEST) as f:
            manifest = json.load(f)
    except Exception:
        return out
    for slug, info in manifest.items():
        if not isinstance(info, dict) or info.get("status") != "done":
            continue
        label = info.get("tag_label") or slug
        path = f"{SCAN_REPORTS_DIR}/{slug}.md"
        try:
            with open(path) as f:
                # 与 _count_candidates_in_report 同一口径 (扣掉黑名单市场, 用户 2026-07-12)
                n = _count_candidates_in_report(f.read())
        except Exception:
            n = 0
        if n > 0:
            out.append((slug, label, n))
    return out


def run_for_slot(scan_slot):
    """一轮完整选品: 对每个有候选的 tag 串行跑 GLM。由 auto_scheduler 在扫描完成后调用。"""
    # 审查修复⑦: 非阻塞抢锁 (整轮跟另一轮/单tag手动触发互斥; 同线程内 run_tag 用 RLock 可重入)
    if not _disc_lock.acquire(blocking=False):
        log.warning("[discovery] 已有一轮选品在跑, 本次触发跳过")
        return
    try:
        _run_for_slot_locked(scan_slot)
    finally:
        _disc_lock.release()


def _run_for_slot_locked(scan_slot):
    _ensure_tables()
    if not is_configured():
        log.info("[discovery] 未配置 ZHIPUAI_API_KEY_DISCOVERY, 跳过选品 (只扫描不分析)")
        return
    tags = _tags_with_candidates()
    if not tags:
        log.info("[discovery] 本轮所有 tag 都没有候选市场, 无需调 GLM")
        return
    # 用户规则: 单 tag 候选 < MIN_CANDIDATES(默认5) → 跳过不送 GLM (省 API); 跳过名单必须写日志, 不许静默。
    eligible = [(s, lb, n) for s, lb, n in tags if n >= MIN_CANDIDATES]
    skipped = [(lb, n) for _, lb, n in tags if n < MIN_CANDIDATES]
    if skipped:
        log.info(f"[discovery] 跳过 {len(skipped)} 个候选不足 {MIN_CANDIDATES} 个的 tag (用户规则省API): " +
                 ", ".join(f"{lb}({n})" for lb, n in skipped))
    if not eligible:
        log.info(f"[discovery] 本轮没有 tag 达到 {MIN_CANDIDATES} 个候选的门槛 → 不调 GLM, 零花费")
        return
    log.info(f"[discovery] 本轮 {len(eligible)} 个 tag 过门槛: " +
             ", ".join(f"{lb}({n})" for _, lb, n in eligible))
    total, ttp, ttc = 0, 0, 0
    t0 = time.time()
    for _, label, _n in eligible:
        n, (tp, tc) = run_tag("", label, scan_slot)
        total += n
        ttp += tp
        ttc += tc
    log.info(f"[discovery] 本轮完成: {total} 条推荐入库, tokens 总计 {ttp}+{ttc}, 耗时 {time.time()-t0:.0f}s → /auto 查看")


# ---------- 流式"扫一个喂一个"多路并发 (用户 2026-07-08: 定时链路专用, 拿最新盘口喂 GLM) ----------

def _count_candidates_in_report(report_text):
    """报告里 '### ' 开头的行数 = 候选市场数, 但**扣掉命中黑名单关键词的市场**
    (用户 2026-07-12: 黑名单市场只搭顺风车, 绝不单独把某 tag 顶过门槛去触发一次 GLM 调用)。
    每个黑名单市场恰好 1 个 '### ' 头 + 1 行带 BLACKLIST_REPORT_MARK 的 slug 行, 直接相减即可。"""
    from modules.tags import BLACKLIST_REPORT_MARK
    lines = (report_text or "").splitlines()
    n_headers = sum(1 for line in lines if line.startswith("### "))
    n_bl = sum(1 for line in lines if BLACKLIST_REPORT_MARK in line)
    return max(0, n_headers - n_bl)


def _record_timeout_run(tag_label, scan_slot, secs):
    """硬超时踢掉一个 tag 时, 补记一条 auto_discovery_runs 报错行 —— 让 dashboard 选品面板显示
    "Tag: 硬超时踢掉" 而不是静默消失 (用户规则: 跳过/失败不许静默)。"""
    try:
        from modules.db import get_conn
        conn = get_conn()
        conn.execute(
            """INSERT INTO auto_discovery_runs (scan_slot, tag, started_at, ok, n_recs, n_invalid,
               followup_used, tokens_prompt, tokens_completion, error) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (scan_slot, tag_label, _utcnow(), 0, 0, 0, 0, 0, 0,
             f"硬超时踢掉 (GLM 处理 > {secs}s 未返回; 卡死调用已丢后台, 其余 tag 照跑)"))
        conn.commit()
        conn.close()
    except Exception:
        log.exception(f"[stream] {tag_label}: 记超时行失败")


def _stream_process_tag(tag_label, scan_slot, mode, configured):
    """一路流水线: 当场即时新扫这个 tag → 数候选 → 够门槛且配了 key 就立刻喂 GLM, 否则跳过。
    GLM 走 _run_tag_locked (它不抢锁; 整轮的 _disc_lock 由 scan_and_discover_stream 顶层持有)。
    返回 (tag_label, n_recs, status)。status: glm / skip:N<M / scan-only / scan-failed / glm-failed / glm-timeout。"""
    from modules import scanner
    slug = scanner._slugify_tag(tag_label)
    # 1. 即时新扫 (复制 scanner._scan_one 的落盘逻辑, 不改 scanner.py; medium 中范围)
    try:
        scanner._update_manifest_entry(slug, status="running", running_at=datetime.now().isoformat())
        t0 = time.time()
        report = scanner.scan_by_tag(tag_label, mode=mode)
        out_path = f"{scanner.SCAN_REPORTS_DIR}/{slug}.md"
        with open(out_path, "w") as f:
            f.write(report)
        scanner._update_manifest_entry(slug, status="done", mtime=time.time(),
                                       elapsed_s=round(time.time() - t0, 1),
                                       report_path=out_path, error=None)
    except Exception as e:
        log.exception(f"[stream] {tag_label}: 即时扫描失败")
        try:
            scanner._update_manifest_entry(slug, status="error", error=str(e)[:200], mtime=time.time())
        except Exception:
            pass
        return (tag_label, 0, "scan-failed")
    # 2. 数候选, 应用 MIN_CANDIDATES 门槛 (跳过必记日志, 不许静默 —— 用户规则9)
    n = _count_candidates_in_report(report)
    if not configured:
        return (tag_label, 0, "scan-only")
    if n < MIN_CANDIDATES:
        log.info(f"[stream] {tag_label}: 候选 {n} < {MIN_CANDIDATES}, 跳过不送 GLM (省API)")
        return (tag_label, 0, f"skip:{n}<{MIN_CANDIDATES}")
    # 3. 立刻喂 GLM —— 报告是这一刻刚扫的, 盘口最新鲜。硬超时熔断 (2026-07-20 用户): 单独子线程跑,
    #    超 TAG_TIMEOUT_S 秒直接踢掉本 tag, 卡死子线程 shutdown(wait=False) 丢后台, 主流程绝不阻塞。
    if TAG_TIMEOUT_S <= 0:
        try:
            n_recs, _tok = _run_tag_locked("", tag_label, scan_slot)
            return (tag_label, n_recs, "glm")
        except Exception:
            log.exception(f"[stream] {tag_label}: GLM 阶段失败")
            return (tag_label, 0, "glm-failed")
    import concurrent.futures as _cf
    _ex = _cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"glm-{slug}")
    _fut = _ex.submit(_run_tag_locked, "", tag_label, scan_slot)
    try:
        n_recs, _tok = _fut.result(timeout=TAG_TIMEOUT_S)
        _ex.shutdown(wait=False)
        return (tag_label, n_recs, "glm")
    except _cf.TimeoutError:
        _ex.shutdown(wait=False)   # 不等卡死的子线程, 让它后台自生自灭 (Python 杀不了线程)
        log.error(f"[stream] {tag_label}: ⏱ GLM 处理超过 {TAG_TIMEOUT_S}s 硬超时 → 踢掉本 tag, 其余继续跑")
        _record_timeout_run(tag_label, scan_slot, TAG_TIMEOUT_S)
        return (tag_label, 0, "glm-timeout")
    except Exception:
        _ex.shutdown(wait=False)
        log.exception(f"[stream] {tag_label}: GLM 阶段失败")
        return (tag_label, 0, "glm-failed")


def scan_and_discover_stream(scan_slot, tier_filter=(1, 2), mode="medium"):
    """定时链路专用: 流式"扫一个喂一个", STREAM_CONCURRENCY 路并发。替代老的 scan_all_tags + run_for_slot。
    每个 tag 丢给 GLM 前当场重扫 → 排后面的类别也拿最新盘口, 不吃旧数据 (用户 2026-07-08 拍板)。
    与 run_for_slot / 手动 discover_now 经同一把 _disc_lock 互斥 (防重复烧 GLM)。"""
    if not _disc_lock.acquire(blocking=False):
        log.warning("[stream] 已有一轮扫描+选品在跑, 本次触发跳过")
        return
    try:
        _ensure_tables()
        _scan_and_discover_stream_locked(scan_slot, tier_filter, mode)
    finally:
        _disc_lock.release()


def _scan_and_discover_stream_locked(scan_slot, tier_filter, mode):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from modules import scanner
    from modules.tags import list_tags_by_tier
    configured = is_configured()
    if not configured:
        log.info("[stream] 未配置 ZHIPUAI_API_KEY_DISCOVERY → 只流式扫描, 不调 GLM (等价老的只扫不评)")
    by_tier = list_tags_by_tier()
    target = []
    for t in tier_filter:
        target.extend(by_tier.get(t, []))
    if not target:
        log.info("[stream] 无目标 tag (tier_filter 空?), 跳过")
        return
    # manifest 全置 pending (跟 scan_all_tags 同款, 保证 dashboard 扫描页显示一致)
    try:
        os.makedirs(scanner.SCAN_REPORTS_DIR, exist_ok=True)
        started = datetime.now().isoformat()
        scanner._write_manifest_atomic({
            scanner._slugify_tag(t): {
                "tag_label": t, "status": "pending", "started_at": started,
                "report_path": f"{scanner.SCAN_REPORTS_DIR}/{scanner._slugify_tag(t)}.md"}
            for t in target})
    except Exception:
        log.exception("[stream] manifest 初始化失败 (不致命, 继续)")
    conc = max(1, STREAM_CONCURRENCY)
    log.info(f"[stream] 开始流式扫描+选品: {len(target)} 个 tag, {conc} 路并发, mode={mode}, "
             f"门槛 {MIN_CANDIDATES} (扫一个喂一个, 拿最新盘口)")
    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=conc) as pool:
        futs = [pool.submit(_stream_process_tag, tag, scan_slot, mode, configured) for tag in target]
        for f in as_completed(futs):
            try:
                results.append(f.result())
            except Exception:
                log.exception("[stream] 某 tag 处理线程异常")
    total_recs = sum(r[1] for r in results)
    glm_tags = [r[0] for r in results if r[2] == "glm"]
    skipped = [(r[0], r[2]) for r in results if r[2].startswith("skip")]
    failed = [r[0] for r in results if r[2] in ("scan-failed", "glm-failed")]
    timed_out = [r[0] for r in results if r[2] == "glm-timeout"]
    if skipped:
        log.info(f"[stream] 跳过 {len(skipped)} 个候选不足 {MIN_CANDIDATES} 的 tag (省API): " +
                 ", ".join(f"{t}({s})" for t, s in skipped))
    if timed_out:
        log.warning(f"[stream] ⏱ {len(timed_out)} 个 tag GLM 硬超时被踢 (>{TAG_TIMEOUT_S}s): " + ", ".join(timed_out))
    if failed:
        log.warning(f"[stream] {len(failed)} 个 tag 处理失败: " + ", ".join(failed))
    log.info(f"[stream] 完成: 送 GLM {len(glm_tags)} 个 tag, 入库 {total_recs} 条推荐, "
             f"耗时 {time.time()-t0:.0f}s → /auto 查看")


# ---------- 页面 + API (routes 由 autobot.py 注册, 不改 dashboard.py) ----------

AUTO_HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AUTO 候选清单</title>
<style>
body{font-family:-apple-system,'PingFang SC',sans-serif;background:#0a0a14;color:#e8e8ff;margin:0;padding:18px}
h2{margin:6px 0 2px}.sub{color:#9898c8;font-size:13px;margin-bottom:14px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-bottom:22px}
th,td{border-bottom:1px solid rgba(255,255,255,.08);padding:6px 8px;text-align:left;vertical-align:top}
th{color:#9898c8;font-weight:500;white-space:nowrap}
.real{color:#00e5a0;font-weight:600}.paper{color:#ffc040;font-weight:600}
.dim{color:#6868b0}.mono{font-family:ui-monospace,monospace}
.err{color:#ff4070}
</style></head><body>
<h2>🤖 AUTO 候选清单</h2>
<div class="sub">GLM 自动选品产出 (第2步: 只列清单, 不买不进测试仓)。分流预演: 0.40&lt;现价&lt;0.85 → 真买, 否则测试仓。每30s自动刷新。</div>
<div id="runs"></div><div id="cands">加载中...</div>
<script>
async function load(){
  const r = await fetch('/api/auto/candidates'); const d = await r.json();
  const rs = d.runs||[], cs = d.candidates||[];
  let h = '<table><tr><th>轮次(slot)</th><th>标签</th><th>推荐</th><th>无效</th><th>追问</th><th>tokens(入+出)</th><th>错误</th></tr>';
  for(const x of rs){h += `<tr><td class="mono">${x.scan_slot||''}</td><td>${x.tag||''}</td><td>${x.n_recs}</td><td>${x.n_invalid}</td><td>${x.followup_used?'是':''}</td><td class="mono">${x.tokens_prompt}+${x.tokens_completion}</td><td class="err">${x.error||''}</td></tr>`}
  document.getElementById('runs').innerHTML = h + '</table>';
  let c = '<table><tr><th>时间</th><th>标签</th><th>市场</th><th>方向</th><th>现价</th><th>q</th><th>信心</th><th>止损档</th><th>分流预演</th><th>理由</th></tr>';
  for(const x of cs){
    const rt = x.route==='real' ? '<span class="real">🟢 会真买</span>' : '<span class="paper">🧪 进测试仓</span>';
    c += `<tr><td class="dim mono">${(x.created_at||'').slice(5,16)}</td><td>${x.tag||''}</td><td><b>${x.title||x.slug}</b><br><span class="dim mono">${x.slug}</span></td><td>${x.side}</td><td class="mono">$${(+x.cur_price).toFixed(3)}</td><td class="mono">${Math.round(x.q*100)}%</td><td>${x.confidence||'-'}</td><td>${x.stop_loss_tier||'-'}</td><td>${rt}</td><td class="dim">${x.reason||''}</td></tr>`}
  document.getElementById('cands').innerHTML = c + '</table>';
}
load(); setInterval(load, 30000);
</script></body></html>"""


def register_routes(app):
    from flask import jsonify, request

    @app.route("/auto")
    def auto_page():
        return AUTO_HTML

    @app.route("/api/auto/candidates")
    def auto_candidates_api():
        _ensure_tables()
        from modules.db import get_conn
        conn = get_conn()
        conn.row_factory = None
        cands = [dict(zip([c[0] for c in cur.description], row)) for cur in
                 [conn.execute("SELECT * FROM auto_candidates ORDER BY id DESC LIMIT 200")]
                 for row in cur.fetchall()]
        runs = [dict(zip([c[0] for c in cur.description], row)) for cur in
                [conn.execute("SELECT * FROM auto_discovery_runs ORDER BY id DESC LIMIT 40")]
                for row in cur.fetchall()]
        conn.close()
        return jsonify({"candidates": cands, "runs": runs})

    @app.route("/api/auto/discover_now", methods=["POST"])
    def discover_now():
        """手动触发一轮选品 (测试用)。body 可带 {"tag": "Iran"} 只跑单个 tag。"""
        _ensure_tables()
        if not is_configured():
            return jsonify({"ok": False, "message": "未配置 ZHIPUAI_API_KEY_DISCOVERY"})
        tag = ((request.get_json(silent=True) or {}).get("tag") or "").strip()
        slot = "manual-" + datetime.now().strftime("%m%d-%H%M%S")
        if tag:
            threading.Thread(target=run_tag, args=("", tag, slot), daemon=True).start()
        else:
            threading.Thread(target=run_for_slot, args=(slot,), daemon=True).start()
        return jsonify({"ok": True, "slot": slot, "message": "已在后台开跑, 看 /auto 或 bot.log"})
