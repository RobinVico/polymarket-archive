"""AUTO 流水线 第3+4步: 分流执行 + 自动下单 (用户 2026-07-08 "全部自动现在开始")。

选品产出的 auto_candidates (status='new') → 逐条执行:
  按**执行时刻的新鲜盘口价**套用户写死的分流规则 (0.40 < p < 0.85):
    → 真买:   /api/suggested_size 计算器金额 → /api/buy_position (executor.buy, 自动 negRisk/tick)
              → 等仓位同步 → /api/record_position 自动录 meta → 候选标 'bought'
    → 测试仓: /api/paper/add (auto_size, 零成本盯价, 进去后零操作) → 候选标 'paper'
  跳过场景全部点名记 status (已持有/公式金额<$1/日限额/仓位数满/盘口缺失/gamma查不到), 绝不静默。

内部走本机 HTTP 复用 dashboard 现成路由 (buy_position/record_position/paper/add/suggested_size),
跟手动操作/今天实测过的是同一条代码路径, 零重复实现。

额度 (用户 2026-07-08 拍板: **不要任何限制**, "到时候有的话我会再跟你说"):
  AUTO_TRADER_DAILY_CAP_USD  = 0    每天真买总额上限; **0 = 不限 (默认)**。auto_trades 台账照记。
  AUTO_TRADER_MAX_POSITIONS  = 0    最多同时持仓数 (含手动仓); **0 = 不限 (默认)**。
  单仓金额 = sizing 公式 (1/4 Kelly, 硬边界 $1~15, cluster cap, 月DD预算) — 用户沿用认可的老计算器,
  它自带的 cluster 20% 上限仍管相关性集中度; **月度回撤预算已删** (2026-07-18 用户拍板, env SIZING_MONTHLY_DD_BUDGET=999999 = 功能性删除)。
"""
import os
import re
import json
import time
import logging
import threading
from datetime import datetime, timezone

import requests as rq

log = logging.getLogger("auto_trader")

BASE = "http://127.0.0.1:5052"
# 用户 2026-07-08 拍板: 不要任何买入额度限制 (原 $10/天、8 仓上限是 Claude 擅自加的默认值, 已撤)。
# 0 = 不限; 以后用户要限制, 改这两个 env 即可, 判断逻辑都留着。
DAILY_CAP_USD = float(os.environ.get("AUTO_TRADER_DAILY_CAP_USD", "0"))
MAX_POSITIONS = int(os.environ.get("AUTO_TRADER_MAX_POSITIONS", "0"))
PAPER_FALLBACK_USD = float(os.environ.get("AUTO_TRADER_PAPER_FALLBACK_USD", "5"))
# 审查修复⑩ (2026-07-08): 'new' 候选的保鲜期 — 超过这么多小时还没被执行 (典型: manual 轮次遗留 /
# 执行当轮失败残留) 就作废, 不许拿几天前的行情推荐去下今天的单。
CANDIDATE_TTL_H = float(os.environ.get("AUTO_TRADER_CANDIDATE_TTL_H", "24"))
# 审查修复③ (2026-07-08 用户拍板): 临下单价格漂移容差 — "看价→算金额→下单"是秒级流程, 正常行情
# 动不了多少; 临下单再复核一次盘口, 相对算金额那次漂移超过这么多 pp (默认 3) = 异动 (90变85那种),
# 这单不追, 点名跳过。值别设太小 (免得正常小抖动全被拒)。
MAX_DRIFT_PP = float(os.environ.get("AUTO_TRADER_MAX_DRIFT_PP", "3"))
# 用户 2026-07-11 拍板: 冻结"每仓 Kelly 用的本金", 让每仓金额【不随现金增长】(加现金 → 多开仓, 不放大单仓)。
# sizing 公式一个字不改 — edge 越大下越多的层次全保留; 只是 Kelly 那步 (raw = 本金 × kelly_f × ¼)
# 用这个固定参考本金, 而不是实时总资产。cluster 上限 (= 真实本金 × 20%) 和 DD 预算仍按【真实】本金/敞口算,
# 所以现金越多 → cluster 房间越大 = 能容更多仓。
#   AUTO_KELLY_BANKROLL_REF = 0  → 不冻结, 用实时本金 (老行为, 默认); 设成 50 = 每仓永远按 $50 盘子算金额。
KELLY_BANKROLL_REF = float(os.environ.get("AUTO_KELLY_BANKROLL_REF", "0"))
# 用户 2026-07-12 拍板: 把置信度 (high/medium/low) 也算进金额 — 高→下多点, 中→正常, 低→下少点。
# 做成 Kelly 那步的乘数 (= 按信心缩放"下注本金"): 只放大/缩小 raw, 后面 天数/冷门/cluster/DD/硬边界照旧夹,
# 所以 high 绝不会冲破 cluster 上限或 $15 顶, low 也不会跌破 $1 硬底 (低于就不下)。sizing.py 一个字不改。
# 幅度可 env 调; 认不出的信心值 → 按 medium(×1.0) 处理。
CONF_MULT = {
    "high":   float(os.environ.get("AUTO_CONF_MULT_HIGH", "1.25")),
    "medium": float(os.environ.get("AUTO_CONF_MULT_MEDIUM", "1.0")),
    "low":    float(os.environ.get("AUTO_CONF_MULT_LOW", "0.75")),
}
# 审查修复⑦ (2026-08): 并发锁 — 定时 execute_for_slot 和手动 /api/auto/execute_now 同时触发时
# 只允许一个在跑 (两个线程同时读同一批 'new' 候选会双买同一市场)。
_run_lock = threading.Lock()


def _suggested_size(q, p, confidence, tier, days, cluster_id):
    """替代内部 HTTP /api/suggested_size (2026-07-11 用户拍板): 同一个 sizing 计算器、同样的输入,
    唯一区别 = Kelly 那步的"本金"可被 AUTO_KELLY_BANKROLL_REF 冻结, 让每仓金额不随现金涨 (加钱→多开仓)。
      - kelly_br  : 冻结参考本金 (env>0) 否则真实本金 → 决定单仓 Kelly 大小 (公式其余照旧: edge 层次全保留);
      - cluster_cap = 真实本金 × 20% (照旧, 随现金涨 = 更多仓房间);
      - dd_exp      = 真实已暴露 drawdown (2026-07-18 起预算=999999, 该闸已被用户删除, 仅留计算)。
    KELLY_BANKROLL_REF=0 (默认) → kelly_br = 真实本金 = 跟老 /api/suggested_size 逐字节等价。
    返回 (size_usd: float, reason: str); 本金 API 挂了返回 (0.0, msg)。"""
    from modules.sizing import position_size_usd, _cfg
    from modules.clusters import bankroll_usd, cluster_exposure_usd, portfolio_exposed_dd_usd
    br_real = bankroll_usd()
    if br_real is None:
        return 0.0, "cash API failed (bankroll unknown)"
    kelly_br = KELLY_BANKROLL_REF if KELLY_BANKROLL_REF > 0 else br_real
    # 信心乘数 (2026-07-12): 高→×1.25 多下, 中→×1.0, 低→×0.75 少下。只缩放 Kelly 那步的"下注本金",
    # 后面 days/冷门/cluster/DD/[$1,$15] 照常夹 → high 不破 cluster 上限/$15 顶, low 不破 $1 底。
    conf_mult = CONF_MULT.get((confidence or "medium").strip().lower(), 1.0)
    cluster_cap = br_real * _cfg("CLUSTER_CAP_PCT")
    cluster_exp = cluster_exposure_usd(cluster_id) if cluster_id else 0.0
    dd_exp = portfolio_exposed_dd_usd()
    size, reason = position_size_usd(
        q=q, p=p, confidence=confidence, stop_loss_tier=tier,
        days_to_resolution=days, bankroll_usd=kelly_br * conf_mult,
        cluster_current_exposure_usd=cluster_exp,
        cluster_cap_usd=cluster_cap, exposed_dd_usd=dd_exp)
    _tags = []
    if KELLY_BANKROLL_REF > 0:
        _tags.append(f"kelly本金冻结${KELLY_BANKROLL_REF:.0f}/真实${br_real:.0f}")
    if conf_mult != 1.0:
        _tags.append(f"信心{confidence}×{conf_mult:g}")
    if _tags:
        reason = "[" + " ".join(_tags) + "] " + reason
    return size, reason


def _ensure_tables():
    from modules.db import get_conn
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS auto_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, day TEXT, slug TEXT, side TEXT,
        usd REAL, ok INTEGER, note TEXT)""")
    conn.commit()
    conn.close()


def _spent_today():
    from modules.db import get_conn
    day = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    v = conn.execute("SELECT COALESCE(SUM(usd),0) FROM auto_trades WHERE day=? AND ok=1", (day,)).fetchone()[0]
    conn.close()
    return float(v or 0)


def _log_trade(slug, side, usd, ok, note=""):
    from modules.db import get_conn
    conn = get_conn()
    conn.execute("INSERT INTO auto_trades (ts, day, slug, side, usd, ok, note) VALUES (?,?,?,?,?,?,?)",
                 (datetime.now(timezone.utc).isoformat(), datetime.now().strftime("%Y-%m-%d"),
                  slug, side, usd, 1 if ok else 0, note[:300]))
    conn.commit()
    conn.close()


def _mark(cand_id, status):
    from modules.db import get_conn
    conn = get_conn()
    conn.execute("UPDATE auto_candidates SET status=? WHERE id=?", (status[:120], cand_id))
    conn.commit()
    conn.close()


def _fresh_ask(token_id):
    try:
        book = rq.get("https://clob.polymarket.com/book", params={"token_id": token_id}, timeout=10).json()
        asks = sorted(float(a["price"]) for a in book.get("asks", []))
        return asks[0] if asks else None
    except Exception:
        return None


def _resolve_token(slug, side):
    """gamma 按 slug 解析 (token_id, closed, 该市场全部 token)。side 匹配 outcomes 文本, 默认 YES=0/NO=1。
    审查修复⑥ (2026-07-08): 多返回 all_tokens, 调用方用它挡"已持有同市场对面方向"(防对锁稳赔价差)。"""
    g = rq.get("https://gamma-api.polymarket.com/markets", params={"slug": slug, "limit": 1}, timeout=10).json()
    if not (g and isinstance(g, list)):
        return None, None, []
    m = g[0]
    closed = (m.get("closed") is True) or (str(m.get("closed")).lower() == "true")
    toks = m.get("clobTokenIds")
    outs = m.get("outcomes")
    toks = json.loads(toks) if isinstance(toks, str) else (toks or [])
    outs = json.loads(outs) if isinstance(outs, str) else (outs or ["Yes", "No"])
    idx = None
    for i, o in enumerate(outs):
        if str(o).strip().upper() == str(side).strip().upper():
            idx = i
            break
    if idx is None:
        idx = 0 if str(side).strip().upper() == "YES" else 1
    tok = toks[idx] if idx < len(toks) else None
    return tok, closed, toks


def _paper_open_exists(token_id):
    """审查修复⑪ (2026-07-08): 同 token 已有未平仓测试仓 → 不重复录 (同一市场每轮反复被推荐会灌爆 paper 表)。"""
    from modules.db import get_conn
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM paper_positions WHERE token_id=? AND status='open' LIMIT 1",
                       (token_id,)).fetchone()
    conn.close()
    return bool(row)


def _in_universe(row):
    """结构性宇宙闸门 (用户 2026-07-08 铁律: "所有的都按原本老的执行, 只代替我手工的部分"):
    只执行「用户白名单 tags 扫描出来的市场」——
      ① 候选的 tag 必须在 modules/tags.py 白名单里;
      ② 候选的 slug 必须真实出现在该 tag 的扫描报告文件里 (证明来自扫描器, 不是凭空来的)。
    任何一条不过 → 真买/测试仓一律拒收, 点名跳过。
    防的是: 手动注入的测试行 / GLM 幻觉出报告里没有的 slug / 任何绕过扫描器的来源。
    (背景: 2026-07-08 E2E 测试注入了体育市场买成了真仓 → 用户炸了, 此闸门保证永不再犯。)

    返回 (ok, why, blacklisted): blacklisted=报告里该市场 slug 行带黑名单标记 (AUTO 2026-07-12 用户拍板)
    → 调用方无视价格强制只进测试仓 (绝不真买)。"""
    from modules.tags import TAGS, BLACKLIST_REPORT_MARK
    from modules.scanner import _slugify_tag, SCAN_REPORTS_DIR
    tag = (row.get("tag") or "").strip()
    if tag not in TAGS:
        return False, f"tag「{tag}」不在白名单", False
    path = f"{SCAN_REPORTS_DIR}/{_slugify_tag(tag)}.md"
    try:
        with open(path) as f:
            content = f.read()
        _slug = (row.get("slug") or "").strip()
        # 审查修复⑭ (2026-07-08): 反引号精确匹配 — 报告里 slug 一律渲染成 "- Slug: `xxx`",
        # 裸子串匹配会让"短 slug 恰好是长 slug 前缀"的幻觉候选漏进来。
        if not _slug or f"`{_slug}`" not in content:
            return False, "slug 不在该 tag 的扫描报告里", False
        # AUTO 2026-07-12: 该市场 slug 行是否带黑名单标记 (scanner 按市场原始标题判定, 比 GLM 改写过的
        # 标题准)。精确匹配 "- Slug: `xxx`" 行, 不会误命中 "- Event Slug:"。
        _bl = False
        _slug_key = f"- Slug: `{_slug}`"
        for _line in content.splitlines():
            if _slug_key in _line:
                _bl = BLACKLIST_REPORT_MARK in _line
                break
    except FileNotFoundError:
        return False, "该 tag 没有扫描报告", False
    return True, "", _bl


def _days_left(end_date):
    try:
        d = datetime.fromisoformat(str(end_date)[:10])
        return max(0, (d.date() - datetime.now().date()).days)
    except Exception:
        return 30


def _trigger_reverse_reeval(row, opp_token, all_toks, held, positions):
    """用户 2026-07-10 拍板 (选项B): 选品给出「已持仓位的反方向」推荐 → 不只是挡对锁,
    还要**立刻触发该持仓一次正规重评**, 并把反向推荐的理由原文塞进重评 prompt
    (pos["_trigger_note"], auto_reeval._build_prompt 会喂给模型)。
    守卫: 重评未启用/仓找不到 → 不动; 已有进行中重评 (inflight) → 不重复;
    同款反向触发 6h 内已发过 → 不重复 (早晚两轮同样反推不重复烧 API)。
    决策走现有管道: 方向纠错闸 + 离线自动执行。任何异常绝不影响执行主流程。"""
    try:
        from modules import auto_reeval
        if not auto_reeval.is_enabled():
            return
        held_tok = next((t for t in all_toks if t and t != opp_token and t in held), None)
        if not held_tok:
            return
        from modules.db import (has_inflight_auto_reeval, save_auto_reeval_pending,
                                get_position_meta, get_conn, _parse_iso_to_aware)
        if has_inflight_auto_reeval(held_tok):
            log.info("[trader] 反向推荐触发重评: 该仓已有进行中重评, 跳过")
            return
        conn = get_conn()
        last = conn.execute(
            "SELECT created_at FROM auto_reeval_suggestions WHERE token_id=? AND trigger_reason LIKE '反向推荐%' "
            "ORDER BY id DESC LIMIT 1", (held_tok,)).fetchone()
        conn.close()
        if last:
            dt = _parse_iso_to_aware(last["created_at"])
            if dt and (datetime.now(timezone.utc) - dt).total_seconds() < 6 * 3600:
                log.info("[trader] 反向推荐触发重评: 6h 内已因同类信号评过, 跳过")
                return
        pos = next((p for p in positions if p.get("asset") == held_tok), None)
        if not pos:
            return
        meta = get_position_meta(held_tok) or {}
        avg = float(pos.get("avg_price") or meta.get("entry_price") or 0)
        cur = float(pos.get("cur_price") or 0)
        loss_pct = (avg - cur) / avg if avg > 0 else 0.0
        sug_id = save_auto_reeval_pending(held_tok, pos, meta, loss_pct, cur, avg)
        trig = (f"反向推荐触发: 选品刚推荐本市场 {row.get('side')} @ {row.get('cur_price')} (q={row.get('q')})")
        conn = get_conn()
        conn.execute("UPDATE auto_reeval_suggestions SET trigger_reason=? WHERE id=?", (trig[:200], sug_id))
        conn.commit()
        conn.close()
        pos = dict(pos)
        pos["_trigger_note"] = (
            f"⚠️ 本次重评的触发原因 (重要背景): 选品 GLM 刚刚推荐了**本市场的反方向** {row.get('side')} "
            f"@ {row.get('cur_price')} (它估 q={row.get('q')}), 其推荐理由原文:「{(row.get('reason') or '')[:300]}」。"
            f"这与我当前持仓方向相反。请把这条反向观点当作重点线索去独立查证 (既不要盲从它, 也不要因为已持仓而护短), "
            f"然后按流程给出 hold / update_q / exit。")
        log.warning(f"[trader] 🔁 反向推荐 → 触发已持仓重评 (id={sug_id}): {(pos.get('title') or '')[:40]}")
        threading.Thread(target=auto_reeval.run_and_store, args=(sug_id, pos, meta), daemon=True).start()
    except Exception:
        log.exception("[trader] 反向推荐触发重评失败 (不影响执行主流程)")


def execute_for_slot(scan_slot=None):
    """执行一轮: scan_slot=None 时执行所有 status='new' 的候选 (手动触发用)。"""
    # 审查修复⑦ (2026-07-08): 非阻塞抢锁 — 已有一轮在跑就直接放弃本次触发 (防双买)。
    if not _run_lock.acquire(blocking=False):
        log.warning("[trader] 已有一轮执行在跑, 本次触发跳过 (防同一候选双买)")
        return
    try:
        _execute_for_slot_locked(scan_slot)
    finally:
        _run_lock.release()


def _execute_for_slot_locked(scan_slot=None):
    from modules.db import get_conn, log_event
    from modules.auto_discovery import route_of
    from modules.executor import Executor
    _ensure_tables()
    conn = get_conn()
    q = "SELECT * FROM auto_candidates WHERE status='new'" + (" AND scan_slot=?" if scan_slot else "") + " ORDER BY id"
    cur = conn.execute(q, (scan_slot,) if scan_slot else ())
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    if not rows:
        log.info("[trader] 没有待执行候选")
        return
    positions = Executor.get().get_positions() or []
    held = {p.get("asset") for p in positions}
    n_pos = len(positions)
    spent = _spent_today()
    _cap_pos = str(MAX_POSITIONS) if MAX_POSITIONS > 0 else "不限"
    _cap_usd = f"{DAILY_CAP_USD:.0f}" if DAILY_CAP_USD > 0 else "不限"
    log.info(f"[trader] 开始执行 {len(rows)} 条候选 | 当前持仓 {n_pos}/{_cap_pos} | 今日已买 ${spent:.2f}/{_cap_usd}")
    bought = papered = skipped = 0
    seen_run = set()   # 审查修复⑤: 本轮内 (slug, side) 去重 — 跨 slot 残留的重复候选只执行第一条
    for row in rows:
        cid, slug, side = row["id"], row["slug"], (row["side"] or "").upper()
        label = f"{slug[:40]} {side}"
        try:
            # 审查修复⑩: 候选过期作废 — 推荐是按当时行情给的, 超过 TTL 不再执行
            try:
                _age_h = (datetime.now(timezone.utc)
                          - datetime.fromisoformat(str(row.get("created_at")))).total_seconds() / 3600.0
            except Exception:
                _age_h = 0.0
            if _age_h > CANDIDATE_TTL_H:
                _mark(cid, f"expired:超{int(CANDIDATE_TTL_H)}h未执行")
                skipped += 1
                log.info(f"[trader] ⏳ 过期作废 ({_age_h:.0f}h 前的推荐): {label}")
                continue
            # 审查修复⑤: 同一轮里同市场同方向只执行第一条 (不同 slot 残留的重复候选)
            if (slug, side) in seen_run:
                _mark(cid, "skipped:本轮重复(同市场同方向)")
                skipped += 1
                continue
            seen_run.add((slug, side))
            ok_u, why, is_bl = _in_universe(row)
            if not ok_u:
                _mark(cid, "skipped:宇宙外:" + why)
                skipped += 1
                log.warning(f"[trader] ⛔ 拒收 (不是白名单tags扫出来的): {label} — {why}")
                continue
            token, closed, all_toks = _resolve_token(slug, side)
            if not token:
                _mark(cid, "skipped:gamma查不到token")
                skipped += 1
                continue
            if closed:
                _mark(cid, "skipped:市场已关闭")
                skipped += 1
                continue
            if token in held:
                _mark(cid, "skipped:已持有")
                skipped += 1
                continue
            # 审查修复⑥: 已持有同市场的对面方向 → 拒买 (买进去 = 和自己对锁, 稳赔一个价差)
            if any(t in held for t in all_toks if t and t != token):
                _mark(cid, "skipped:已持有同市场对面方向(防对锁)")
                skipped += 1
                log.warning(f"[trader] ⛔ 拒买对面方向 (会和已有仓位对锁): {label}")
                # 用户 2026-07-10 拍板: 反向推荐不只是挡掉, 还要立刻触发已持仓位的重评 (带上推荐理由原文)
                _trigger_reverse_reeval(row, token, all_toks, held, positions)
                continue
            fresh = _fresh_ask(token)
            if not fresh or not (0 < fresh < 1):
                _mark(cid, "skipped:无盘口ask")
                skipped += 1
                continue
            route = route_of(fresh)   # 用户规则: 按执行时刻的现价分流 (推荐价可能已漂移)
            # AUTO 2026-07-12 用户拍板: 命中黑名单关键词的市场 → 无视价格强制只进测试仓 (真买通道永远关着)。
            # is_bl 来自扫描报告标记 (scanner 按市场原始标题判定); 强制在真买判定之前, 保证绝不真买。
            if is_bl and route != "paper":
                log.info(f"[trader] 🚫 命中黑名单关键词, 强制改走测试仓 (现价 {fresh} 本可真买): {label}")
                route = "paper"
            if route == "paper":
                # 审查修复⑪: 同 token 已有未平仓测试仓 → 不重复录
                if _paper_open_exists(token):
                    _mark(cid, "paper:已有同仓跳过")
                    skipped += 1
                    log.info(f"[trader] 🧪 测试仓已有同 token 未平仓, 跳过重复录入: {label}")
                    continue
                payload = {"slug": slug, "side": side.lower(), "entry_price": fresh,
                           "q": row.get("q"), "confidence": row.get("confidence") or "medium",
                           "stop_loss_tier": row.get("stop_loss_tier") or "hybrid",
                           "days_to_resolution": row.get("days_to_resolution"),
                           "cluster_id": row.get("cluster_id") or "", "tag": row.get("tag") or "",
                           "reason": (row.get("reason") or "")[:300], "end_date": row.get("end_date") or "",
                           "auto_size": True, "fallback_usd": PAPER_FALLBACK_USD}
                r = rq.post(BASE + "/api/paper/add", json=payload, timeout=30).json()
                if r.get("ok"):
                    _mark(cid, "paper:黑名单强制" if is_bl else "paper")
                    papered += 1
                    if is_bl:
                        # 用户 2026-07-12: 黑名单市场进测试仓要"标注一下" → 主页事件流也记一条
                        log.info(f"[trader] 🧪 命中黑名单关键词, 强制进测试仓 (不真买): {label} @ {fresh}")
                        try:
                            log_event("blacklist_paper", row.get("title") or slug,
                                      f"命中黑名单关键词 → 强制进测试仓 (不真买) {side} @ {fresh}")
                        except Exception:
                            pass
                    else:
                        log.info(f"[trader] 🧪 进测试仓: {label} @ {fresh} (现价在40~85外)")
                else:
                    _mark(cid, "error:paper:" + str(r.get("message"))[:80])
                    log.warning(f"[trader] 测试仓录入失败 {label}: {r.get('message')}")
                continue
            # ===== 真买通道 =====
            if MAX_POSITIONS > 0 and n_pos + bought >= MAX_POSITIONS:   # 0 = 不限 (用户拍板默认)
                _mark(cid, "skipped:持仓数已满")
                skipped += 1
                log.info(f"[trader] 跳过 {label}: 持仓数 {n_pos + bought} 已达上限 {MAX_POSITIONS}")
                continue
            days = row.get("days_to_resolution")
            days = int(days) if days else _days_left(row.get("end_date"))
            usd, size_reason = _suggested_size(
                q=float(row.get("q") or 0), p=fresh,
                confidence=row.get("confidence") or "medium",
                tier=row.get("stop_loss_tier") or "hybrid",
                days=days, cluster_id=(row.get("cluster_id") or "").strip() or None)
            usd = float(usd or 0)
            if usd < 1:
                _mark(cid, f"skipped:公式金额${usd:.2f}<1")
                skipped += 1
                log.info(f"[trader] 跳过 {label}: 计算器给 ${usd:.2f} ({size_reason})")
                continue
            if DAILY_CAP_USD > 0:   # 0 = 不限 (用户拍板默认); 台账 spent 照记
                remaining = DAILY_CAP_USD - spent
                if remaining < 1:
                    _mark(cid, "skipped:日限额已满")
                    skipped += 1
                    log.info(f"[trader] 跳过 {label}: 今日买入已达 ${spent:.2f}/{DAILY_CAP_USD:.0f}")
                    continue
                usd = min(usd, remaining)
            usd = round(usd, 2)
            # 审查修复③: 临下单最后复核盘口 — 跟算金额用的 fresh 比, 漂移 > MAX_DRIFT_PP 视为异动放弃;
            # 顺带确认现价还在 40~85 真买区间 (贴边的候选可能被小漂移带出区间)。
            ask2 = _fresh_ask(token)
            if not ask2 or not (0 < ask2 < 1):
                _mark(cid, "skipped:临下单盘口消失")
                skipped += 1
                continue
            drift_pp = abs(ask2 - fresh) * 100
            if drift_pp > MAX_DRIFT_PP:
                _mark(cid, f"skipped:临下单漂移{drift_pp:.1f}pp>{MAX_DRIFT_PP:g}pp")
                skipped += 1
                log.warning(f"[trader] ⛔ 临下单价格异动 {fresh:.3f}→{ask2:.3f} ({drift_pp:.1f}pp), 放弃: {label}")
                continue
            if route_of(ask2) != "real":
                _mark(cid, "skipped:临下单出40-85区间")
                skipped += 1
                log.info(f"[trader] 临下单现价 {ask2:.3f} 已出真买区间, 放弃: {label}")
                continue
            r = rq.post(BASE + "/api/buy_position",
                        json={"token_id": token, "usd_amount": usd,
                              "reason": f"auto:{scan_slot or 'manual'}"}, timeout=90).json()
            if not r.get("ok"):
                _mark(cid, "error:buy:" + str(r.get("message"))[:100])
                _log_trade(slug, side, usd, False, str(r.get("message"))[:200])
                log.warning(f"[trader] 买入失败 {label}: {r.get('message')}")
                continue
            # 审查修复④: 记"实际成交金额"而非请求金额 (0.001-tick 市场步长凑整会差很多,
            # 实测请求 $4.91 只成交 $3.37)。executor.buy 的消息格式固定 "≈ $X.XX", 解析失败退回请求额。
            msg_txt = str(r.get("message") or "")
            _m_act = re.search(r"≈ \$([0-9]+(?:\.[0-9]+)?)", msg_txt)
            usd_actual = float(_m_act.group(1)) if _m_act else usd
            _log_trade(slug, side, usd_actual, True, msg_txt[:200])
            spent += usd_actual
            bought += 1
            held.add(token)   # 审查修复⑤: 本轮后续候选立刻看到刚买的仓 (不等 data-api 同步)
            log.info(f"[trader] 🟢 已真买: {label} 实际${usd_actual:.2f} (请求${usd:.2f}) @ ~{fresh} | {msg_txt}")
            # 等 data-api 同步出仓位, 拿真实 avg 录 meta
            avg = fresh
            for _ in range(6):
                time.sleep(10)
                for p in (Executor.get().get_positions() or []):
                    if p.get("asset") == token:
                        avg = float(p.get("avg_price") or fresh)
                        break
                else:
                    continue
                break
            # 审查修复⑮: 端点认的键是 slug / original_confidence (老键名保留兼容, 不再靠 gamma 反查兜底)
            # 审查修复③: cluster_id 归一 (端点要求含 '-', GLM 给了不带 '-' 的就置空当未分类, 别让整个档案被拒)
            _cl = (row.get("cluster_id") or "").strip()
            if _cl and "-" not in _cl:
                log.warning(f"[trader] cluster_id「{_cl}」不含'-', 置空录入 (端点会拒): {label}")
                _cl = ""
            rec_ok = False
            rec_msg = ""
            for _try in range(3):   # 审查修复③: 录档案失败自动重试 3 次 (每次刷新实时成交均价)
                rec = rq.post(BASE + "/api/record_position",
                              json={"token_id": token, "slug": slug, "market_slug": slug, "side": side,
                                    "entry_price": avg, "tp": row.get("q"),
                                    "original_confidence": row.get("confidence") or "medium",
                                    "confidence": row.get("confidence") or "medium",
                                    "stop_loss_tier": row.get("stop_loss_tier") or "hybrid",
                                    "cluster_id": _cl, "tag": row.get("tag") or "",
                                    "end_date": row.get("end_date") or "",
                                    "entry_reason": ("[auto] " + (row.get("reason") or ""))[:400]}, timeout=25).json()
                rec_msg = str(rec.get("message") or "")
                if rec.get("ok"):
                    rec_ok = True
                    break
                log.warning(f"[trader] 录档案失败 第{_try+1}/3次 {label}: {rec_msg}")
                if _try < 2:
                    time.sleep(20)
                    for p in (Executor.get().get_positions() or []):
                        if p.get("asset") == token:
                            avg = float(p.get("avg_price") or avg)
                            break
            _mark(cid, "bought" if rec_ok else "bought(meta失败⚠️裸奔)")
            if not rec_ok:
                # 审查修复②③: 录不上档案 = 无止盈止损的裸奔仓 → 红色警示进事件流, 等用户手动补档案
                try:
                    log_event("no_meta_alert", row.get("title") or slug,
                              f"🔴 自动买入后档案录入失败({rec_msg[:80]}) — 该仓暂无止盈止损, 请手动补档案")
                except Exception:
                    pass
                log.warning(f"[trader] 🔴 档案最终录入失败, 该仓裸奔等手动补档案: {label}")
            try:
                log_event("auto_buy", row.get("title") or slug, f"自动买入 ${usd_actual:.2f} {side} @ ~{fresh}")
            except Exception:
                pass
        except Exception as e:
            _mark(cid, ("error:" + str(e))[:120])
            log.exception(f"[trader] 执行候选失败 {label}")
    log.info(f"[trader] 本轮完成: 真买 {bought}, 测试仓 {papered}, 跳过 {skipped} | 今日累计买入 ${spent:.2f}")


def run_execution_consumer(scan_slot, stop_event, poll_s=3.0):
    """流式链路专用执行消费线程 (用户 2026-07-09: "有推荐就立马执行, 其他 tag 继续分析")。

    分析那 4 路并行**只负责把候选写进库**; 这个线程每 ~poll_s 秒轮询一次, 一发现该 slot 有 'new'
    候选就立刻执行 —— **完整复用 execute_for_slot** (宇宙闸/临下单漂移复核/防对锁/日限额/台账/
    录档案重试 全都在, 一字未改), 且下单经 _run_lock **永远串行不打架**; 因为执行会把候选标成非
    'new', 排在后面的轮询/收尾只会捡真正还没执行的, 天然不双买。

    分析线程从不调用执行 → **下单再慢也绝不阻塞分析** (这就是不用"分析线程内联下单"的原因)。
    stop_event 置位 = 分析结束 → 再兜底执行一次把最后写入的候选清掉, 然后退出。"""
    log.info(f"[trader] 执行消费线程启动 (slot={scan_slot}, 每 {poll_s:g}s 轮询待执行候选, 一有就立刻下单)")
    n_loops = 0
    while not stop_event.is_set():
        try:
            execute_for_slot(scan_slot)
        except Exception:
            log.exception("[trader] 执行消费线程轮询异常 (继续轮询, 不中断)")
        n_loops += 1
        stop_event.wait(poll_s)
    # 收尾: 分析都结束了, 把最后一刻写入、可能还没轮询到的候选执行掉
    try:
        execute_for_slot(scan_slot)
    except Exception:
        log.exception("[trader] 执行消费线程收尾执行异常")
    log.info(f"[trader] 执行消费线程结束 (slot={scan_slot}, 轮询 {n_loops} 次)")


def register_routes(app):
    from flask import jsonify, request

    @app.route("/api/auto/execute_now", methods=["POST"])
    def auto_execute_now():
        """手动触发执行所有待执行候选 (测试用)。body 可带 {"slot": "..."} 只执行该轮。"""
        slot = ((request.get_json(silent=True) or {}).get("slot") or "").strip() or None
        threading.Thread(target=execute_for_slot, args=(slot,), daemon=True).start()
        return jsonify({"ok": True, "message": "执行器已在后台开跑, 看 bot.log / /auto / 主页持仓"})
