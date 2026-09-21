"""
v5.13: 大跌自动重评 (auto-reeval on big drawdown).

流程: monitor 心跳发现某仓位亏损 >= 阈值 (默认 30%) → 后台线程调用 Claude API 联网调研
(web_search + web_fetch + adaptive thinking) → 强制 submit_decision 工具输出结构化决策
(hold / update_q / exit) → 写入 auto_reeval_suggestions 表 status='pending' → 用户在
dashboard 对应区块点确认才执行。**不自动卖**。ANTHROPIC_API_KEY 缺失时整个特性静默禁用。

判定口径刻意写进 prompt: 看论点有没有被真新闻推翻 (不是单纯回撤), q 不许只因价跌就锚到现价。
"""
import os
import logging
from datetime import datetime, timezone

log = logging.getLogger("monitor")


def _f(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _i(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


# ---- 可调参数 (env 可覆盖, 不用改代码) ----
LOSS_THRESHOLD = _f("AUTO_REEVAL_LOSS_PCT", 0.30)     # 亏 >= 30% 触发
COOLDOWN_HOURS = _f("AUTO_REEVAL_COOLDOWN_H", 6)      # v5.15: 同一仓位自动重评冷却 6 小时 (清空也不立刻再评); 手动「🤖 API重评」按钮绕过
RETRIGGER_DROP_PCT = _f("AUTO_REEVAL_RETRIGGER_DROP", 0.05)  # AUTO 2026-07-18: 事件型从"持有期最好点"回撤≥这么多就再触发一次重评 (默认 5pp; 无时间冷却)
MANUAL_ESCALATE_MIN = _f("AUTO_REEVAL_MANUAL_ESCALATE_MIN", 2)  # v6.0.5: 在线时 manual 卡闪烁这么多分钟无人确认 → 自动调 API (离线立即接管)
CENTER_WINDOW_H = _i("AUTO_REEVAL_CENTER_WINDOW_H", 24)   # v7.0 反锚定: "大跌前中枢"取多长的 trailing 窗口(小时)
CENTER_SKIP_H = _i("AUTO_REEVAL_CENTER_SKIP_H", 6)        # v7.0 反锚定: 排除最近这么多小时(大跌发生段), 让中枢反映"跌之前"
EXIT_GUARD_EDGE = _f("AUTO_REEVAL_EXIT_GUARD_EDGE", 0.08) # v7.0 事件型 exit 护栏: edge 需 ≤ -这么多 (或论点破) 才放行 exit
MODEL = os.environ.get("AUTO_REEVAL_MODEL", "claude-opus-4-8")
MAX_TOKENS = _i("AUTO_REEVAL_MAX_TOKENS", 10000)       # v5.13.2 省钱档: 封顶输出(含思考)
MAX_ROUNDS = _i("AUTO_REEVAL_MAX_ROUNDS", 10)          # agentic 循环上限 (防跑飞); 正常 1-3 轮就够
EFFORT = os.environ.get("AUTO_REEVAL_EFFORT", "medium") # v5.13.2 省钱: low/medium/high; medium 砍思考输出, 保 Opus 质量
_ENABLED = os.environ.get("AUTO_REEVAL_ENABLED", "1") not in ("0", "false", "False", "")

# ---- 多模型: v7.x 默认主用 Claude (权威, 驱动显示+离线自动执行), 智谱 GLM 降为备用 (Claude 挂了顶上) ----
# 配置: .env 加 ZHIPUAI_API_KEY=xxx 启用 GLM; ANTHROPIC_API_KEY 启用 Claude。两个都配 = 双跑对比。
# AUTO_REEVAL_PRIMARY=glm 可把 GLM 提回第一 (Claude 仅兜底); 默认 claude 优先。
# AUTO_REEVAL_DUAL=1 (默认): 每次重评两个模型都并行跑, GLM 输出只进「API重评」对比页
#   (主列/主页/面板永远是权威=Claude, GLM 绝不在别处显示、绝不当权威除非 Claude 挂了)。
#   =0 退回省钱串行: 主用成功就不跑备用。
# v6.0.8: GLM 便宜 → 参数全拉满: 模型 glm-5.2 (1M上下文/128K输出) + thinking enabled + reasoning_effort=max
#         + 专业版搜索 search_pro + 多取结果 + content_size=high。任何高级参数 SDK 不认 → _glm_create 自动降级。
GLM_MODEL = os.environ.get("AUTO_REEVAL_GLM_MODEL", "glm-5.2")    # 最强文本模型; 可换 glm-4.7 / glm-4.6
GLM_MAX_TOKENS = _i("AUTO_REEVAL_GLM_MAX_TOKENS", 32000)          # 含思考 token; glm-5.2 上限 128K, 32K 给深推理留足空间
GLM_REASONING_EFFORT = os.environ.get("AUTO_REEVAL_GLM_REASONING", "max")  # 思考深度拉满 (glm-5.2 强制思考)
GLM_SEARCH_COUNT = _i("AUTO_REEVAL_GLM_SEARCH_COUNT", 20)         # 联网取多少条结果 (默认才5, 拉到20)
GLM_SEARCH_ENGINE = os.environ.get("AUTO_REEVAL_GLM_SEARCH_ENGINE", "search_pro")  # 专业版搜索
GLM_TEMP = _f("AUTO_REEVAL_GLM_TEMP", 0.6)
PRIMARY = os.environ.get("AUTO_REEVAL_PRIMARY", "claude").strip().lower()
DUAL_COMPARE = os.environ.get("AUTO_REEVAL_DUAL", "1") not in ("0", "false", "False", "")


def _glm_key():
    return os.environ.get("ZHIPUAI_API_KEY") or os.environ.get("ZHIPU_API_KEY")

def _claude_key():
    return os.environ.get("ANTHROPIC_API_KEY")

def _provider_order():
    """返回这次该按什么顺序试的模型列表 (有 key 的才进)。默认 glm 优先, claude 兜底。"""
    has_glm, has_claude = bool(_glm_key()), bool(_claude_key())
    if PRIMARY == "claude":
        order = (["claude"] if has_claude else []) + (["glm"] if has_glm else [])
    else:
        order = (["glm"] if has_glm else []) + (["claude"] if has_claude else [])
    return order


def is_configured():
    """功能是否装好 = 总开关开 且 至少有一个模型的 key (忽略紧急暂停)。
    monitor 用它判断 %止损要不要交给重评 —— 即使紧急暂停, 也别盲卖, 而是冻结在 PENDING_REEVAL。"""
    return _ENABLED and bool(_provider_order())

def is_enabled():
    """现在是否真能调 API = 装好 且 没被紧急暂停 (API模式)。auto 触发 / 手动 🤖 / 离线执行 都看这个。"""
    if not is_configured():
        return False
    try:
        from modules.db import get_api_paused
        if get_api_paused():
            return False
    except Exception:
        pass
    return True


# ---- submit_decision: 程序读这个结构 ----
DECISION_TOOL = {
    "name": "submit_decision",
    "description": "联网调研完成后, 调用本工具提交对该持仓的最终结构化决策。必须调用本工具, 不要只用文字回答。",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["hold", "update_q", "exit"],
                "description": "hold=继续持有(自动止损照旧); update_q=继续持有但更新概率估计; exit=立即/提前止损(清仓)",
            },
            "new_q": {
                "type": "number",
                "description": "0-1 之间。重新校准的'持有方向最终兑现'的概率, 必须从基本面+新闻推导, 不许只因现价低就压低。",
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "thesis_broken": {
                "type": "boolean",
                "description": "仅作标记: 是否有重大不利事件真正推翻原始论点 (单纯价格波动=false)。这不是决策前提 — 没有重大事件你照样可以 update_q / hold / 在 edge 转负时 exit。",
            },
            "headline_event": {
                "type": "string",
                "description": "若 thesis_broken=true, 一句话说明是什么事件; 否则一句话说明本次 q 判断的核心依据 (如 '民调小幅走弱' / '无重大变化, 维持原判' 等)。",
            },
            "reason": {"type": "string", "description": "2-4 句中文理由。"},
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关键一手来源 URL (可为空数组)。",
            },
        },
        "required": ["action", "new_q", "confidence", "thesis_broken", "headline_event", "reason", "sources"],
        "additionalProperties": False,
    },
}

WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    # max_content_tokens: 限制单页抓取上限, 防大页面/PDF 爆 token (官方建议, web_fetch 工具本身免费但抓回内容按 token 计费)
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_content_tokens": 8000},
]

PROMPT_TMPL = """你是 Polymarket 持仓风控分析师。下面这个持仓出现了大幅回撤, 需要你**联网调研最新一手信息**后给出处置决策。

# 持仓
市场: {title}
slug: {slug}
方向: 持有 {side}（{side} 兑现我就赢, 价格涨=我赚）
入场均价: ${avg:.3f}（我的成本）
当前价: ${cur:.3f}
浮动盈亏: {pnl:+.1f}%
距结算: {days} 天
Resolution 规则: {desc}

# 任务
联网查与该 resolution 直接相关的最新进展（官方表态 / 数据公布 / 权威报道 / 民调等）,
**从零重新评估 q（持有方向最终兑现的概率）**, 然后给出处置决策。

# 判定纪律
1. 价格跌 ≠ 论点一定错。事件驱动型市场常因消息震荡, 价格不完全等于真相。
2. q 必须基于你的调研（resolution 规则 + 基本面 + 带日期的新闻/数据）独立得出, 不要机械地照着现价反推 q。
   但只要调研支持, **你完全可以、也应该更新 q（调高或调低都行）, 不需要一定有"重大事件"才能动 q**。
3. 决策依据 = 你重估的 q 对当前价的 edge（扣掉滑点+手续费约 2-3pp 后的实际可获取值）+ 是否有重大不利变化:
   - edge 仍明显为正 → hold, 或 update_q（继续持有但把 q 更新成你的最新判断）。
   - edge 转负 / 论点明显走弱 → exit。
4. "关键机构长期不更新 / 本该发生的事迟迟不发生" 也算逆向信号, 应反映到 q 里。

# 调研要求
- 至少做 3-5 次独立搜索, 优先一手来源, 必要时抓取关键页面全文。
- 聚焦最近的、能影响该 resolution 的硬信息。

# 输出（必须）
你可以选 4 种处置 (action):
- hold: 继续持有, 自动止损照旧 (跌到止损线仍会自动卖)
- update_q: 继续持有, 但把 q 更新成你最新判断
- exit: 立即/提前止损 (现在卖出)

调研完成后, **必须调用 submit_decision 工具**输出结构化决策。不要只用文字回答。
"""


def _days_left(end_date):
    if not end_date:
        return None
    try:
        dt = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # naive 当 UTC, 防减法崩
        return (dt - datetime.now(timezone.utc)).days
    except Exception:
        return None


def _pre_dump_center(token_id, cur_price, hist=None):
    """v7.0 反锚定: 估"大跌之前"的价格中枢, 给重评当价格参照 (而不是被砸下去的现价 —— 那是 #79/#86 卖飞的根)。
    方法: 取 prices-history trailing 窗口、排除最近 CENTER_SKIP_H 小时(大跌发生段), 取中位数(稳健、无需调参)。
    数据不足 / 跟现价几乎一样 → None (调用方降级, 重评照常不受影响)。永不抛异常。"""
    try:
        if hist is None:
            from modules.executor import Executor
            hist = Executor.get().get_prices_history(token_id, interval="max", fidelity="60")
        prices = [float(h["p"]) for h in (hist or []) if h.get("p") is not None]
        if len(prices) < 8:
            return None
        skip = max(0, int(CENTER_SKIP_H))
        win = int(CENTER_WINDOW_H)
        seg = prices[-(win + skip):-skip] if skip > 0 else prices[-win:]
        if len(seg) < 4:  # 窗口取不到 → 退而求其次, 用"除最近 skip 段"的全段
            seg = prices[:-skip] if (skip > 0 and len(prices) > skip) else prices
        if len(seg) < 4:
            return None
        s = sorted(seg); n = len(s)
        center = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0
        if center <= 0 or center >= 1:
            return None
        if cur_price and abs(center - float(cur_price)) < 0.01:
            return None  # 跟现价基本一样 = 没有"大跌前中枢"可言, 别给无意义参照
        return round(center, 4)
    except Exception:
        return None


def guard_event_driven_exit(action, decision, tier, cur_price):
    """v7.0 安全闸: event_driven 仓的 exit 必须 (论点被真新闻推翻 thesis_broken) 或 (edge 明显为负 ≤ -EXIT_GUARD_EDGE)
    才放行, 否则降级为 update_q(应用 new_q、继续持有)。返回 (action_eff, downgraded, why)。
    纯函数, 不碰 DB / 不卖。非 exit / 非 event_driven → 原样返回。
    默认安全: new_q 缺失/不可解析 且 非 thesis_broken → 不放行(持有), 绝不在坑底盲卖事件型。"""
    if action != "exit" or tier != "event_driven":
        return (action, False, "")
    thesis_broken = bool((decision or {}).get("thesis_broken"))
    edge = None
    try:
        nq = (decision or {}).get("new_q")
        if nq is not None and cur_price and float(cur_price) > 0:
            edge = float(nq) - float(cur_price)
    except Exception:
        edge = None
    honor = thesis_broken or (edge is not None and edge <= -float(EXIT_GUARD_EDGE))
    if honor:
        return ("exit", False, "")
    edge_txt = f"{edge*100:+.1f}pp" if edge is not None else "未知(new_q缺失)"
    why = (f"event_driven 护栏: exit 降级为 update_q (论点未破 + edge {edge_txt} > "
           f"-{int(EXIT_GUARD_EDGE*100)}pp; 事件型常先砸后弹, 不在坑底砍, 继续持有)")
    return ("update_q", True, why)


APPEND_DECISION_INSTRUCTION = """

---
# ⚙️ 自动重评模式 (Claude API 联网执行 — 本段是给 API 的附加指令)
你有 web_search / web_fetch 工具。请按上面的要求**联网调研最新一手信息**, 独立重估 q。
**调研完成后必须调用 submit_decision 工具**给出结构化决策 (4 选 1), 不要只输出文字或 JSON:
- hold = 继续持有 (自动止损照旧)
- update_q = 继续持有但更新 q (只要调研支持就可调高/调低, 不需一定有"重大事件")
- exit = 立即/提前止损 (现在卖)
q 必须从基本面 + 带日期的新闻推导, **不许只因现价低就锚到现价**。
"""

# v6.0.7: GLM 不用 Anthropic 的 submit_decision 工具, 改成"联网后只输出一个 JSON 对象"再由程序解析。
GLM_JSON_INSTRUCTION = """

---
# ⚙️ 自动重评模式 (智谱 GLM 联网执行 — 本段覆盖上面任何"调用 submit_decision 工具"的说法)
你有 web_search 联网工具。请先**联网调研最新一手信息**, 独立重估 q (持有方向最终兑现的概率, 0~1)。
**调研结束后, 最终那条回复只输出一个 JSON 对象** (调研阶段可反复调用 web_search 工具; 但最终回复里不要再调用任何工具, JSON 前后不要任何多余文字或解释), 字段:
{
  "action": "hold | update_q | exit",
  "new_q": 0~1 的小数 — ⚠️ 方向硬性要求: 必须是「我持有的那个方向」(标的信息里的 side) 兑现的概率, **绝不是 YES 方向的概率**; 我持 NO 时 new_q = NO 兑现概率 (例: 你判断 YES 只有 10% → 我持 NO → new_q 填 0.90 不是 0.10)。必须从基本面+带日期的新闻推导, 不许只因现价低就锚到现价; new_q 直接填你的原始判断 (不做任何往市价的校准/收缩, 原始判断多少就是多少),
  "confidence": "high | medium | low",
  "thesis_broken": true 或 false (是否有重大不利事件真正推翻原始论点; 单纯价格波动=false),
  "headline_event": "一句话: thesis_broken 时说明是什么事件, 否则说明本次 q 判断的核心依据",
  "reason": "2-4 句中文理由",
  "sources": ["关键一手来源URL", "..."]
}
action 含义: hold=继续持有(止损照旧) / update_q=继续持有但更新 q / exit=立即止损清仓。
⚠️ JSON 格式硬性要求 (否则程序解析失败): reason / headline_event 等字符串值**内部禁止出现英文双引号 \"**, 需要引用就用中文引号「」; 字符串内**不要换行**; 严格合法 JSON。
再次强调: 只输出上面这个 JSON 对象, 不要任何多余文字。
"""


def _build_prompt(pos, meta, glm=False):
    """v5.15: 统一用'手动复制给 Claude'的同一份 reeval prompt (build_reeval_prompt) + 附加 submit_decision 指令。
    构造失败则退回内置 PROMPT_TMPL, 保证不挂。"""
    meta = dict(meta or {})
    cur = float(pos.get("cur_price") or 0)
    center = pos.get("_pre_dump_center")  # v7.0: run_and_store 预先算好挂在 pos 上 (None=数据不足/没大跌)
    center_note = ""
    if center is not None:
        center_note = (f"\n\n⚠️ 反锚定: 已知该仓「大跌前」稳健价格中枢 ≈ {center*100:.0f}% "
                       f"(现价 {cur*100:.0f}% 是大跌后被压低价)。q 以 基本面 + resolution + 这个大跌前中枢 为准, "
                       f"明确不要锚定到被压低的现价。")
    # AUTO 分叉补丁 (2026-07-10 用户拍板): 触发方(如"选品推荐了反方向")可在 pos["_trigger_note"] 挂说明,
    # 原文喂进重评 prompt — 让模型知道自己为什么被叫醒、带着那条反向理由去查证。
    _trigger_note = ("\n\n" + str(pos.get("_trigger_note"))) if pos.get("_trigger_note") else ""
    center_note = center_note + _trigger_note
    try:
        from modules.prompts import build_reeval_prompt
        token_id = pos.get("asset")
        # 拉 Gamma question + resolution 规则原文 (跟 /api/reeval_prompt 那条手动 prompt 完全一致)
        try:
            import requests as _req
            gr = _req.get("https://gamma-api.polymarket.com/markets",
                          params={"clob_token_ids": token_id, "limit": 1}, timeout=8).json()
            if gr and isinstance(gr, list) and gr:
                if gr[0].get("question"):
                    meta["_market_question"] = gr[0]["question"]
                if gr[0].get("description"):
                    meta["_market_description"] = gr[0]["description"]
        except Exception:
            pass
        days = _days_left(meta.get("end_date"))
        base = build_reeval_prompt(meta, cur, days if days is not None else 0, pre_dump_center=center)
        return base + (GLM_JSON_INSTRUCTION if glm else APPEND_DECISION_INSTRUCTION) + center_note
    except Exception as e:
        log.warning(f"auto_reeval: 手动 prompt 构造失败, 退回内置模板: {e}")
        avg = float(pos.get("avg_price") or meta.get("entry_price") or 0)
        pnl = ((cur - avg) / avg * 100) if avg > 0 else 0
        side = pos.get("outcome") or meta.get("side") or "?"
        days = _days_left(meta.get("end_date"))
        base = PROMPT_TMPL.format(
            title=pos.get("title", ""),
            slug=meta.get("market_slug") or "",
            side=str(side).upper(),
            avg=avg, cur=cur, pnl=pnl,
            days=(days if days is not None else "?"),
            desc=(meta.get("notes") or "(dashboard 未存 resolution 原文; 请按市场标题与 slug 联网查证)"),
        )
        return (base + GLM_JSON_INSTRUCTION if glm else base) + center_note


VALID_ACTIONS = ("hold", "update_q", "exit", "cancel_autostop")


def _run_one(prov, pos, meta):
    """跑单个 provider, 返回合法 decision (带 _provider) 或 {'error':..., '_provider':prov}。绝不抛异常。"""
    try:
        d = _run_glm(pos, meta) if prov == "glm" else _run_claude(pos, meta)
    except Exception as e:
        d = {"error": f"{type(e).__name__}: {e}"}
    if d and "error" not in d and d.get("action") in VALID_ACTIONS:
        d["_provider"] = prov
        return d
    return {"error": (d or {}).get("error", "无有效决策"),
            "_provider": prov, "raw_text": (d or {}).get("raw_text", "")}


def run_reeval_dual(pos, meta):
    """v7.x 编排: 同时跑所有已配置模型 (并行) 给对比用; 权威决策按 _provider_order() 取第一个成功的。
    返回 {"authoritative": <decision|{'error'}>, "by_provider": {"claude":..., "glm":...}}。
    - 默认主用 Claude → 权威=Claude, 挂了降级 GLM (用户确认: 离线时 GLM 可顶上动真钱)。
    - DUAL_COMPARE=1 (默认): 两个都跑 (并行), 即使 Claude 成功也跑 GLM 纯为对比页。
    - DUAL_COMPARE=0: 退回省钱串行 (主用成功就不跑备用)。
    防御: 任一 provider 异常/非法决策 → 记错继续, 绝不把坏决策当权威。"""
    order = _provider_order()
    if not order:
        return {"authoritative": {"error": "未配置任何模型 key (ANTHROPIC_API_KEY / ZHIPUAI_API_KEY)"},
                "by_provider": {}}
    by = {}
    if DUAL_COMPARE and len(order) > 1:
        import threading as _th
        def _work(pp):
            by[pp] = _run_one(pp, pos, meta)   # 各线程写不同 key, GIL 下安全
        threads = [_th.Thread(target=_work, args=(p,), daemon=True) for p in order]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    else:
        for p in order:                         # 省钱串行: 第一个成功就停 (老行为)
            by[p] = _run_one(p, pos, meta)
            if "error" not in by[p]:
                break
    authoritative = next((by[p] for p in order if p in by and "error" not in by[p]), None)
    if authoritative is None:
        errs = " | ".join(f"{p}: {(by.get(p) or {}).get('error', '?')}" for p in order if p in by)
        return {"authoritative": {"error": "所有模型都失败: " + errs}, "by_provider": by}
    if authoritative.get("_provider") != order[0]:
        log.info(f"auto_reeval: 主模型({order[0]})未成功, 权威决策降级到 {authoritative.get('_provider')}")
    return {"authoritative": authoritative, "by_provider": by}


def run_auto_reeval(pos, meta):
    """向后兼容包装: 只取权威决策 (老调用方用)。新代码用 run_reeval_dual 拿两家对比。"""
    return run_reeval_dual(pos, meta)["authoritative"]


def _run_claude(pos, meta):
    """同步调用 Claude API (在后台线程里跑)。返回 decision dict, 或 {'error': ...}。"""
    import anthropic

    client = anthropic.Anthropic(timeout=600.0, max_retries=2)
    tools = WEB_TOOLS + [DECISION_TOOL]
    messages = [{"role": "user", "content": _build_prompt(pos, meta)}]
    raw_text = []
    decision = None
    forced = False

    try:
        use_effort = bool(EFFORT)
        for _ in range(MAX_ROUNDS):
            kwargs = dict(
                model=MODEL, max_tokens=MAX_TOKENS, tools=tools,
                messages=messages, thinking={"type": "adaptive"},
            )
            if use_effort:
                kwargs["output_config"] = {"effort": EFFORT}   # v5.13.2 省钱: 控制思考深度/输出花费
            if forced:
                kwargs["tool_choice"] = {"type": "tool", "name": "submit_decision"}
            try:
                resp = client.messages.create(**kwargs)
            except TypeError:
                # 老 SDK 不认 output_config → 去掉降级重试 (一次性), 不影响功能
                if use_effort:
                    use_effort = False
                    kwargs.pop("output_config", None)
                    resp = client.messages.create(**kwargs)
                else:
                    raise

            for b in resp.content:
                bt = getattr(b, "type", None)
                if bt == "text":
                    raw_text.append(b.text or "")
                elif bt == "tool_use" and getattr(b, "name", None) == "submit_decision":
                    decision = dict(b.input)
            if decision is not None:
                break

            sr = resp.stop_reason
            messages.append({"role": "assistant", "content": resp.content})

            if sr == "refusal":
                return {"error": "模型安全拒绝 (refusal), 无法调研该标的"}
            if sr == "pause_turn":
                continue  # 服务端联网工具还没跑完, 再发一次继续
            # end_turn / tool_use / max_tokens 但没给决策 → 逼它调用 submit_decision
            if forced:
                break  # 已经强制过一次还不给 → 放弃
            messages.append({
                "role": "user",
                "content": "请基于上面的调研, 现在立即调用 submit_decision 工具给出最终结构化决策, 不要再继续搜索。",
            })
            forced = True

        if decision is None:
            return {"error": "未拿到结构化决策 (模型未调用 submit_decision)",
                    "raw_text": " ".join(raw_text)[:1000]}
        decision["raw_text"] = " ".join(raw_text)[:2000]
        return decision
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _glm_regex_extract(s):
    """v6.0.8 兜底: 严格 JSON 崩了 (多半是中文自由文本里有未转义的 ") 时, 按已知 schema 用正则抠字段。
    actionable 字段 (action/new_q/confidence/thesis_broken) 类型简单 → 可靠; 自由文本 + sources 尽力。
    返回 dict (至少有合法 action) 或 None。"""
    import re
    if not s:
        return None
    act = re.search(r'"action"\s*:\s*"(hold|update_q|exit|cancel_autostop)"', s)
    if not act:
        return None
    out = {"action": act.group(1)}
    mq = re.search(r'"new_q"\s*:\s*([0-9]*\.?[0-9]+)', s)
    out["new_q"] = mq.group(1) if mq else None
    mc = re.search(r'"confidence"\s*:\s*"(high|medium|low)"', s)
    out["confidence"] = mc.group(1) if mc else "medium"
    mt = re.search(r'"thesis_broken"\s*:\s*(true|false)', s, re.I)
    out["thesis_broken"] = bool(mt and mt.group(1).lower() == "true")
    mh = re.search(r'"headline_event"\s*:\s*"(.*?)"\s*,\s*"reason"', s, re.S)
    out["headline_event"] = mh.group(1) if mh else ""
    mr = re.search(r'"reason"\s*:\s*"(.*?)"\s*,\s*"sources"', s, re.S) or re.search(r'"reason"\s*:\s*"(.*?)"\s*[}\]]', s, re.S)
    out["reason"] = mr.group(1) if mr else ""
    out["sources"] = list(dict.fromkeys(re.findall(r'https?://[^\s"\\\]]+', s)))[:10]
    return out


def _parse_glm_decision(text):
    """从 GLM 的文本里抠出 JSON 决策并校验。返回标准 decision dict 或 {'error': ...}。
    防御: 只接受合法 action; new_q 容错 (字符串/百分数→0-1); update_q 必须有 new_q。"""
    import re, json as _json
    raw = (text or "").strip()
    if not raw:
        return {"error": "GLM 空响应"}
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    blob = m.group(1) if m else None
    if blob is None:
        i, j = raw.find("{"), raw.rfind("}")
        blob = raw[i:j + 1] if (i >= 0 and j > i) else None
    if not blob:
        return {"error": "GLM 未返回 JSON 决策", "raw_text": raw[:1000]}
    d = None
    try:
        d = _json.loads(blob)
    except Exception:
        # 容错: GLM 常在中文自由文本字段里塞未转义的英文 " / 换行 → 严格 JSON 崩。
        # schema 固定, 用正则按字段抠 (actionable 字段类型简单, 一定能拿到; 自由文本尽力)。
        d = _glm_regex_extract(blob)
    if d is None:
        return {"error": "GLM JSON 解析失败 (含正则兜底)", "raw_text": raw[:1000]}
    action = str(d.get("action") or "").strip()
    if action not in ("hold", "update_q", "exit", "cancel_autostop"):
        return {"error": f"GLM 非法 action: {action!r}", "raw_text": raw[:1000]}
    nq = d.get("new_q")
    if nq is not None:
        try:
            nq = float(nq)
            if nq > 1:               # 万一给了百分数 (如 65)
                nq = nq / 100.0
            nq = max(0.0, min(1.0, nq))
        except Exception:
            nq = None
    if action == "update_q" and nq is None:
        return {"error": "GLM update_q 但 new_q 缺失/非法", "raw_text": raw[:1000]}
    src = d.get("sources")
    return {
        "action": action,
        "new_q": nq,
        "confidence": str(d.get("confidence") or "medium"),
        "thesis_broken": bool(d.get("thesis_broken")),
        "headline_event": str(d.get("headline_event") or ""),
        "reason": str(d.get("reason") or ""),
        "sources": [str(u) for u in src][:8] if isinstance(src, list) else [],
    }


def _glm_create(client, **kwargs):
    """容错调用 GLM: 若 SDK 不认某个高级参数 (TypeError) 就按 optional 顺序逐个去掉重试。
    只对 TypeError(参数不被 SDK 接受) 降级; 真正的 API 错误照常抛出 → 编排器降级到 Claude。"""
    optional = ["extra_body", "thinking", "temperature", "max_tokens"]  # 去掉的优先顺序
    while True:
        try:
            return client.chat.completions.create(**kwargs)
        except TypeError:
            for k in optional:
                if k in kwargs:
                    log.warning(f"GLM: SDK 不认参数 {k}, 去掉重试")
                    kwargs.pop(k)
                    break
            else:
                raise


def _nq_flip_suspect(new_q, ref):
    """AUTO 分叉: new_q 疑似填成了对面方向? (离 参考q 很远, 但 1-new_q 离参考 q 很近 → 像镜像翻转)"""
    try:
        direct = abs(float(new_q) - float(ref))
        mirror = abs((1.0 - float(new_q)) - float(ref))
        return direct > 0.35 and mirror < 0.15
    except Exception:
        return False


def _confirm_new_q_direction(client, messages, raw_text, d, pos, meta):
    """AUTO 分叉补丁 (用户 2026-07-08 定的规则): new_q 必须是「持有方向」的概率;
    数值疑似填成对面方向 → **直接反问 GLM 本人**要正确方向 (全自动, 不甩给用户)。
    反问也确认不了 → 返回 error = 本轮按模型失败处理 (不动仓位, 安全默认)。
    背景: 实测 id=2 GLM 把持 NO 应填 0.90 的 new_q 填成了 YES 方向的 0.10。"""
    import re as _re
    try:
        if d.get("action") not in ("update_q", "exit") or d.get("new_q") is None:
            return d
        new_q = float(d["new_q"])
        ref = None
        for k in ("new_tp", "tp"):
            try:
                v = float((meta or {}).get(k) or 0)
                if 0 < v < 1:
                    ref = v
                    break
            except Exception:
                pass
        if ref is None:
            try:
                c = float(pos.get("cur_price") or 0)
                if 0 < c < 1:
                    ref = c
            except Exception:
                pass
        if ref is None or not _nq_flip_suspect(new_q, ref):
            return d
        # 审查修复② 附带 (2026-07-08): executor 归一化的仓位字典键叫 "side", 老代码读 "outcome" 永远取不到
        side = str(pos.get("side") or pos.get("outcome") or (meta or {}).get("side") or "?").upper()
        cur = float(pos.get("cur_price") or 0)
        log.warning(f"auto_reeval 方向嗅探: new_q={new_q} 疑似对面方向 (持有 {side}, 参考 q={ref:.2f}) → 反问 GLM 确认")
        ask = (f"确认一个字段的方向: 我持有的是 {side} (当前 {side} 市价 {cur:.2f}, 我原估 {side} 概率 {ref:.2f})。"
               f"你刚才给的 new_q={new_q}。规则: new_q 必须是「{side} 方向兑现」的概率。"
               f'请重新确认后, 只输出一个 JSON, 不要任何其他文字: {{"new_q_held_side": 0到1的小数}}')
        msgs = list(messages) + [{"role": "assistant", "content": (raw_text or "")[:50000]},
                                 {"role": "user", "content": ask}]
        resp = _glm_create(client, model=GLM_MODEL, messages=msgs,
                           max_tokens=2000, temperature=0.1, thinking={"type": "enabled"})
        t = ""
        try:
            m = resp.choices[0].message
            t = (getattr(m, "content", None) or "") or (getattr(m, "reasoning_content", None) or "")
        except Exception:
            pass
        mt = _re.search(r"new_q_held_side\"?\s*[:=]\s*(0?\.\d+|1(?:\.0+)?|0(?:\.0+)?)", t or "")
        if not mt:
            return {"error": f"new_q 方向可疑 (={new_q}, 持有{side} 参考{ref:.2f}) 且反问未获确认 → 本轮放弃"}
        fixed = float(mt.group(1))
        if not (0 < fixed < 1):
            return {"error": f"new_q 方向反问返回越界值 {fixed} → 本轮放弃"}
        if abs(fixed - new_q) < 0.05:
            log.info(f"auto_reeval 方向反问: GLM 坚持 new_q={fixed} (判定为真·大变盘, 非方向错)")
        else:
            log.info(f"auto_reeval 方向反问: GLM 更正 new_q {new_q} → {fixed}")
        d["new_q"] = fixed
        d["reason"] = (d.get("reason") or "") + f" [方向已与GLM确认: 持有{side}方向 q={fixed}]"
        # 审查修复① (2026-07-08 用户拍板): new_q 被更正过 (说明原分析把方向搞反了) 且原决定是 exit
        # → 原 exit 是基于反方向 q 给的, 不能照抄 —— 再追问 GLM 一次"基于更正后的 q 还卖不卖", 按最终答案执行;
        # 追问拿不到合法答案 → 本轮放弃不动仓 (跟方向确认失败同样的保守缺省)。
        if d.get("action") == "exit" and abs(fixed - new_q) >= 0.05:
            ask2 = (f"你刚才已把 new_q 更正为 {fixed} (= 我持有的 {side} 方向兑现概率, 当前 {side} 市价 {cur:.2f})。"
                    f"你之前给的处置是 exit(清仓), 但那是在 new_q 方向填反时给的。"
                    f"现在基于更正后的 new_q={fixed} 重新决定处置, 只输出一个 JSON, 不要任何其他文字: "
                    f'{{"final_action": "hold 或 update_q 或 exit 或 cancel_autostop"}}')
            msgs2 = msgs + [{"role": "assistant", "content": (t or "")[:20000]},
                            {"role": "user", "content": ask2}]
            resp2 = _glm_create(client, model=GLM_MODEL, messages=msgs2,
                                max_tokens=1500, temperature=0.1, thinking={"type": "enabled"})
            t2 = ""
            try:
                m2msg = resp2.choices[0].message
                t2 = (getattr(m2msg, "content", None) or "") or (getattr(m2msg, "reasoning_content", None) or "")
            except Exception:
                pass
            mfa = _re.search(r'"?final_action"?\s*[:=]\s*"(hold|update_q|exit|cancel_autostop)"', t2 or "")
            if not mfa:
                return {"error": f"new_q 方向更正后 exit 是否维持未获 GLM 确认 → 本轮放弃 (不动仓)"}
            fa = mfa.group(1)
            if fa != d["action"]:
                log.warning(f"auto_reeval 二次确认: 方向更正后 GLM 把处置 exit → {fa}")
            d["action"] = fa
            d["reason"] = (d.get("reason") or "") + f" [方向更正后二次确认处置={fa}]"
        return d
    except Exception as e:
        log.warning(f"auto_reeval 方向确认流程异常: {e} → 保守放弃本轮")
        return {"error": f"new_q 方向确认异常: {e}"}


def _run_glm(pos, meta):
    """v6.0.8: 同步调用智谱 GLM (参数拉满: thinking + reasoning_effort=max + search_pro 多结果 + 大输出)。
    返回 decision dict 或 {'error': ...}。任何异常/非法决策都 → 编排器降级到 Claude。绝不返回坏决策。"""
    from zhipuai import ZhipuAI  # 没装/没 key → 抛异常 → 编排器降级
    try:
        client = ZhipuAI(timeout=600.0)   # 深度思考可能慢, 给足超时
    except TypeError:
        client = ZhipuAI()                # 老 SDK 不认 timeout
    prompt = _build_prompt(pos, meta, glm=True)
    query = (pos.get("title") or meta.get("market_slug") or "").strip()[:78]
    messages = [
        {"role": "system", "content": "你是 Polymarket 持仓风控分析师。先用 web_search 联网查最新一手信息, 充分思考后, 只输出一个 JSON 决策对象。"},
        {"role": "user", "content": prompt},
    ]
    # AUTO 分叉补丁 (用户 2026-07-09 拍板): 多轮自主搜索 agent 优先 (像 Claude 一样搜→想→再搜),
    # 失败自动回退老的一次性注入搜索。AUTO_GLM_AGENTIC=0 整体关闭回老路。
    text = ""
    _agent_sources = []
    resp = None
    _agent_ok = False
    try:
        from modules.auto_glm_agent import AGENTIC_ON as _AG_ON
    except Exception:
        _AG_ON = False
    if _AG_ON:
        try:
            from modules.auto_glm_agent import agentic_analyze
            _r = agentic_analyze(
                api_key=_glm_key(), model=GLM_MODEL,
                system_msg=("你是 Polymarket 持仓风控分析师。你有一个可反复调用的 web_search 工具, "
                            "像研究员一样多轮使用: 先查该市场 resolution 相关的最新进展, 有疑点再深挖查证 "
                            "(一次一个查询词)。调研充分后, 最终那条回复只输出一个 JSON 决策对象。"),
                user_prompt=prompt, max_tokens=GLM_MAX_TOKENS,
                temperature=GLM_TEMP, reasoning=GLM_REASONING_EFFORT,
                log_prefix="auto_reeval")
            text = _r["text"]
            _agent_sources = _r["sources"]
            _agent_ok = True
            log.info(f"auto_reeval GLM agent 自主搜索 {_r['n_searches']} 次完成")
        except Exception as _ae:
            log.warning(f"auto_reeval GLM 多轮搜索 agent 失败 ({_ae}), 回退一次性注入搜索")
    if not _agent_ok:
        tools = [{"type": "web_search", "web_search": {
            "enable": True,
            "search_engine": GLM_SEARCH_ENGINE,   # 专业版搜索
            "search_query": query,
            "search_result": True,                # 回传来源链接
            "count": GLM_SEARCH_COUNT,            # 多取结果 (默认才5)
            "content_size": "high",               # 每条抓更多正文
        }}]
        resp = _glm_create(
            client,
            model=GLM_MODEL, messages=messages, tools=tools,
            max_tokens=GLM_MAX_TOKENS, temperature=GLM_TEMP,
            thinking={"type": "enabled"},                       # 开思考 (glm-5.2 本就强制思考)
            extra_body={"reasoning_effort": GLM_REASONING_EFFORT},  # 思考深度拉满
        )
        try:
            _msg = resp.choices[0].message
            text = (getattr(_msg, "content", None) or "")
            if not text.strip():  # v7.1: thinking 开启时部分 SDK/模型把内容放 reasoning_content, content 可能空
                text = (getattr(_msg, "reasoning_content", None) or "")
        except Exception:
            return {"error": "GLM 响应结构异常 (无 choices/content)"}
    d = _parse_glm_decision(text)
    if "error" in d:
        return d
    # AUTO 分叉: new_q 方向可疑 → 反问 GLM 本人确认 (用户 2026-07-08 规则; 确认不了=本轮放弃不动仓)
    d = _confirm_new_q_direction(client, messages, text, d, pos, meta)
    if "error" in d:
        return d
    # AUTO 分叉 (2026-07-18 起, 2026-07-20 收口): REEVAL prompt 里的"打五折"校准已**物理删除**, GLM 直接给
    # 原始判断 new_q; 校准统一挪到这里做一次 = 市场价 + 0.8×(new_q_raw − 市场价)。(手动流程无此步 → 用原始)
    # ⚠️ 放在方向纠错闸【之后】: 让翻转嗅探/exit二次确认仍按 GLM **原始**数判 (校准位移不干扰方向判定);
    # 校准后的值供存储/展示/离线执行/edge 判定。GLM 原始值仍在 d["raw_text"] 里可审计。
    try:
        if d.get("new_q") is not None:
            from modules.auto_calibrate import calibrate_q
            _cur = float(pos.get("cur_price") or 0)
            if _cur > 0:
                _raw = float(d["new_q"])
                _cal = calibrate_q(_raw, _cur)
                d["new_q"] = _cal
                if abs(_cal - _raw) > 1e-9:
                    log.info(f"auto_reeval: new_q 校准 raw {_raw:.3f} → {_cal:.3f} (市价 {_cur:.3f}, 信自己八成)")
    except Exception:
        log.exception("auto_reeval: new_q 校准异常 (保留 GLM 原值继续)")
    # 补充来源: agent 自主搜索攒的链接 + (回退路径时) GLM web_search 回传的链接
    try:
        urls = list(_agent_sources or [])
        ws = getattr(resp, "web_search", None) if resp is not None else None
        for w in (ws or []):
            link = (w.get("link") or w.get("url")) if isinstance(w, dict) else (getattr(w, "link", None) or getattr(w, "url", None))
            if link:
                urls.append(str(link))
        if urls:
            d["sources"] = list(dict.fromkeys((d.get("sources") or []) + urls))[:10]
    except Exception:
        pass
    d["raw_text"] = text[:2000]
    return d


def _auto_execute(sug_id, d, pos, meta):
    """v5.14: 离线时直接执行 AI 决策 (动真钱)。守卫: 只执行合法 action, 全程 log, exit 重新拉实时仓位。"""
    from modules.db import (set_auto_reeval_status, update_auto_reeval_error, apply_auto_reeval_q,
                            set_autostop_disabled, log_event, clear_position_meta, save_closed_position,
                            update_monitor_state, get_position_meta, claim_auto_reeval)
    action = (d or {}).get("action")
    token_id = pos.get("asset")
    title = pos.get("title", "")
    try:
        # v6.0.1 (#6): 原子抢占, 与 dashboard 确认按钮互斥, 防同一建议被两条路同时执行 → 双卖
        if not claim_auto_reeval(sug_id):
            log.info(f"auto_reeval id={sug_id}: 已被确认/其他抢占, 跳过离线自动执行")
            return
        # AUTO 分叉 (2026-07-18 用户最高指令): 删除事件型 exit 护栏 (原需"论点被重大新闻推翻 thesis_broken
        #   或 edge≤-8pp"才放行, 否则降级 update_q)。现在 GLM 一判 exit 立刻执行, 不问新闻大小/够不够 8 个点。
        #   ⚠️ 只删这道"不让卖"的护栏; 方向纠错闸 _confirm_new_q_direction (防 GLM 把胜率数字填反) 保留在决策生成阶段。
        if action == "exit":
            from modules.executor import Executor
            exe = Executor.get()
            live = next((p for p in (exe.get_positions() or []) if p.get("asset") == token_id), None)
            if not live:
                set_auto_reeval_status(sug_id, "executed")
                log.info(f"auto_reeval id={sug_id}: exit 但仓位已不在, 归档")
                return
            mp = get_position_meta(token_id) or {}
            size = live.get("size") or 0
            avg = live.get("avg_price") or mp.get("entry_price") or 0
            cur = live.get("cur_price") or 0
            side = live.get("outcome") or mp.get("side") or ""
            ok = exe.sell(token_id, size, "auto_reeval:exit(离线自动)")
            if not ok:
                # v6.0.1 (#4 修): 卖失败/部分成交(executor <95% 返 False) → 不静默搁置/不记 error,
                # 改挂 pending (会进紧急弹窗) 让你看到 + 确认重试; 剩余仓不丢、meta 不清。
                set_auto_reeval_status(sug_id, "pending")
                log.warning(f"auto_reeval id={sug_id}: 离线自动卖出未完成(可能部分成交), 改挂 pending 等确认重试")
                return
            log_event("auto_sell", title, f"AUTO_REEVAL(离线自动) exit size={size}")
            try:
                save_closed_position(token_id=token_id, market_slug=mp.get("market_slug") or title,
                    side=side, avg_entry=avg, exit_price=cur, size=size,
                    exit_reason="AUTO_REEVAL:exit(离线自动)", stop_loss_tier=mp.get("stop_loss_tier"),
                    claude_raw_estimate=mp.get("claude_raw_estimate") or mp.get("tp"),
                    entry_at=mp.get("created_at"), cluster_id=mp.get("cluster_id"), tag=mp.get("tag"))
            except Exception as e:
                log.warning(f"save_closed_position failed (sell ok): {e}")
            clear_position_meta(token_id)
            set_auto_reeval_status(sug_id, "executed")
            log.info(f"auto_reeval id={sug_id}: 离线自动清仓 {title[:30]}")
        elif action == "update_q":
            nq = d.get("new_q")
            if nq is not None:
                nq = max(0.01, min(0.99, float(nq)))  # v6.0.1 (#7): 夹 [0.01,0.99], 防 AI 返回越界 q 污染 edge 计算
                apply_auto_reeval_q(token_id, nq)
                try:
                    from modules.executor import Executor
                    from modules.monitor import HOLD_MIN_EDGE_PP, SOFT_NEGATIVE_THRESHOLD_PP
                    live = next((p for p in (Executor.get().get_positions() or []) if p.get("asset") == token_id), None)
                    cur = float(live.get("cur_price")) if live else 0
                    if cur > 0:
                        edge = (float(nq) - cur) * 100
                        ns = "HOLD" if edge > HOLD_MIN_EDGE_PP else ("MARGINAL" if edge >= SOFT_NEGATIVE_THRESHOLD_PP else "SOFT_NEGATIVE")
                        update_monitor_state(token_id, ns)
                except Exception:
                    pass
            set_auto_reeval_status(sug_id, "executed")
            log.info(f"auto_reeval id={sug_id}: 离线自动 update_q → {nq}")
        elif action == "cancel_autostop":
            # AUTO 2026-07-18 用户拍板: 删掉 cancel_autostop 选项 — 即使模型返回也【不再关止损】, 一律按 hold 处理。
            set_auto_reeval_status(sug_id, "executed")
            log.info(f"auto_reeval id={sug_id}: cancel_autostop 已停用 → 按 hold 处理 (不关自动止损)")
        else:  # hold
            set_auto_reeval_status(sug_id, "executed")
            log.info(f"auto_reeval id={sug_id}: 离线决策 hold, 无操作")
    except Exception as e:
        try:
            update_auto_reeval_error(sug_id, f"离线执行异常: {type(e).__name__}: {e}")
        except Exception:
            pass
        log.warning(f"auto_reeval id={sug_id}: 离线执行异常: {e}")


def run_and_store(sug_id, pos, meta, force_manual=False):
    """后台线程入口: 跑 API → 写回。
    force_manual=True (用户手动点「🤖 API重评」): 永远只挂 pending 等手动确认, 不管在不在线都不自动执行。
        ——这个按钮是"人在外面快速一键重评"用的, 结果一定弹出来等用户拍板, 绝不自动动钱。
    force_manual=False (monitor 大跌自动触发): 离线 → 直接自动执行(动真钱); 在线(中途回来) → 留 pending 等批准。"""
    from modules.db import update_auto_reeval_decision, update_auto_reeval_error
    # 审查修复② (2026-07-08 用户拍板): 无档案仓一律不重评 —— 方向/q/止损档无从谈起,
    # 老行为会把方向默认成 YES (持 NO 时整个重评反着来还自动执行)。红色警示写进事件流,
    # 用户看盘时手动补档案, 补完自然恢复重评。巡检和大跌触发两条路都被这里挡住。
    if not (meta or {}).get("side"):
        try:
            update_auto_reeval_error(sug_id, "无档案仓不重评 (用户规则 2026-07-08): 请先在主页给该仓补录档案(方向/q/止损档)")
        except Exception:
            pass
        try:
            from modules.db import log_event
            log_event("no_meta_alert", pos.get("title") or "",
                      "🔴 无档案仓已跳过重评 — 请手动补录档案 (方向/q/止损档), 补完才恢复重评/止盈止损管理")
        except Exception:
            pass
        log.warning(f"auto_reeval id={sug_id}: 🔴 无档案仓跳过重评 (等用户补档案): {(pos.get('title') or '')[:40]}")
        return
    _curve_json = None
    try:
        # v7.0: 算一次"大跌前中枢"+价格曲线 — 挂 pos 给 prompt 反锚定用, 挂 d 给落库校准用 (失败→None, 不影响重评)
        try:
            import json as _json
            from modules.executor import Executor
            _tok = pos.get("asset")
            _hist = Executor.get().get_prices_history(_tok, interval="max", fidelity="60")
            pos["_pre_dump_center"] = _pre_dump_center(_tok, pos.get("cur_price"), hist=_hist)
            _curve = [[h.get("t"), h.get("p")] for h in (_hist or []) if h.get("t") is not None][-200:]
            _curve_json = _json.dumps(_curve) if _curve else None
        except Exception:
            pos["_pre_dump_center"] = None
        res = run_reeval_dual(pos, meta)
        d = res["authoritative"]
        if "error" in d:
            update_auto_reeval_error(sug_id, d["error"])
            log.warning(f"auto_reeval id={sug_id} 失败: {d['error']}")
            return
        d["_pre_dump_center"] = pos.get("_pre_dump_center")
        d["_price_curve_json"] = _curve_json
        # v7.x: 两模型完整输出存 compare_json, 只给「API重评」对比页; 主列=权威(默认 Claude), 别处不显示 GLM
        try:
            import json as _cj
            d["_compare_json"] = _cj.dumps(res.get("by_provider") or {}, ensure_ascii=False, default=str)
        except Exception:
            d["_compare_json"] = None
        update_auto_reeval_decision(sug_id, d)   # 置 status='pending'
        _bp = res.get("by_provider") or {}
        _summ = ", ".join(f"{k}={'ok' if 'error' not in (v or {}) else 'err'}" for k, v in _bp.items())
        log.info(f"auto_reeval id={sug_id} → action={d.get('action')} 权威={d.get('_provider')} "
                 f"thesis_broken={d.get('thesis_broken')} conf={d.get('confidence')} [对比: {_summ}]")
        # v5.16: 手动 API重评 (force_manual) 永远挂 pending 等手动确认, 不管在不在线; 只有 monitor 自动触发才在离线时自动执行。
        from modules.db import get_presence
        if force_manual:
            log.info(f"auto_reeval id={sug_id}: 手动 API重评 → 挂起等手动确认 (force_manual, 不管在不在线都不自动执行)")
        elif get_presence().get("effective_online", False):
            log.info(f"auto_reeval id={sug_id}: 你在线 → 挂起等批准 (不自动执行)")
        else:
            _auto_execute(sug_id, d, pos, meta)
    except Exception as e:
        try:
            update_auto_reeval_error(sug_id, f"{type(e).__name__}: {e}")
        except Exception:
            pass
        log.warning(f"auto_reeval id={sug_id} 线程异常: {e}")
