"""三号账户 shadow 独立监控页 (2026-07-24 用户要求, 照 /bench 的钦定模式做)。

`/shadow` 页 = **主页 (auto_dashboard) 的克隆换数据源** (8.5.1 用户返工令: "别乱改, 共用部件保持原有的"):
  导航(含小恐龙)/指标磁贴/资产总值曲线(区间按钮+成本线+区间涨跌头)/当前持仓面板 —— HTML/CSS/JS
  逐行照搬 auto_bench_dashboard (它本身就是主页克隆), 只把接口换成 /api/shadow/*; 绝不自己发挥。
  shadow 专属内容 (已了结战绩 / 全部条目 / 候选处理审计 / shadow事件流 / 手动扫描) 用同款卡片放下方。
接口形状刻意对齐主页同名接口 (holdings/history), 让照搬的 JS 一字不改就能跑。
数据全部只读自 shadow 自己的表/实例; 绝不碰主账户/bench (隔离铁则见 auto_shadow.py)。
"""
import time
import logging
from datetime import datetime, timezone

log = logging.getLogger("auto_shadow")

_cash_cache = (0.0, None)   # 页面 30s 轮询, 现金查询加 30s 缓存 (绝不用 Executor._live_cash 类属性)


def _cached_cash():
    global _cash_cache
    from modules import auto_shadow as sh
    if _cash_cache[1] is not None and time.time() - _cash_cache[0] < 30:
        return _cash_cache[1]
    c = sh._cash()
    if c is not None:
        _cash_cache = (time.time(), c)
    return c if c is not None else _cash_cache[1]


def _days_left(end_date):
    if not end_date:
        return None
    try:
        dt = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt - datetime.now(timezone.utc)).days
    except Exception:
        return None


def _build_holdings():
    """形状对齐 auto_dashboard._build_holdings → 主页照搬来的 renderHoldings/renderMetrics JS 直接吃。
    数据源 = shadow 钱包实时仓位 (auto_shadow._positions) + shadow_positions 表 (side/止损线) +
    LEFT JOIN auto_candidates (q/信心/tag/end_date, 经 cand_id)。"""
    from modules import auto_shadow as sh
    sh._ensure_tables()
    live = sh._positions()
    meta_rows = sh._db_rows(
        "SELECT sp.token_id, sp.side, sp.stop_price, ac.q, ac.confidence, ac.tag, ac.end_date "
        "FROM shadow_positions sp LEFT JOIN auto_candidates ac ON ac.id = sp.cand_id "
        "WHERE sp.status IN ('open','pending')")
    meta = {m["token_id"]: m for m in meta_rows}
    rows = []
    total_pnl = total_cost = total_value = 0.0
    for p in (live or []):
        cp = p.get("cur_price") or 0
        ap = p.get("avg_price") or 0
        sz = p.get("size") or 0
        if sz <= 0:
            continue
        m = meta.get(p.get("asset")) or {}
        pnl_pct = ((cp - ap) / ap * 100) if ap > 0 else 0
        pd = (cp - ap) * sz
        rows.append({
            "asset": p.get("asset"), "title": p.get("title", "") or "",
            "side": (m.get("side") or "").upper(), "avg_price": ap, "cur_price": cp,
            "size": sz, "value": cp * sz, "pnl_pct": pnl_pct, "pnl_dollar": pd,
            "days_left": _days_left(m.get("end_date")),
            "q": m.get("q"), "confidence": m.get("confidence"), "tag": m.get("tag"),
            "stop_price": m.get("stop_price"),
        })
        total_pnl += pd
        total_cost += ap * sz
        total_value += cp * sz
    cash = _cached_cash()
    cash = cash if cash is not None else 0
    return {"ok": live is not None, "positions": rows, "total_pnl": total_pnl,
            "total_cost": total_cost, "total_value": total_value, "cash": cash,
            "assets_total": total_value + cash, "position_count": len(rows)}


def _history(rng):
    """形状对齐主页 loadChart 吃的 {ok,range,points:[{ts,assets_total,cost_line}],deposits,note}。
    shadow 单笔入金无需出入金校正。"""
    from modules import auto_shadow as sh
    sh._ensure_tables()
    now = int(time.time())
    since = {"1d": now - 86400, "1w": now - 7 * 86400, "1m": now - 30 * 86400,
             "1y": now - 365 * 86400}.get(rng, 0)
    rows = sh._db_rows("SELECT ts, cash, pos_value, pos_cost, total FROM shadow_snapshot ORDER BY ts")
    pts = []
    for r in rows:
        cost_line = (r["pos_cost"] + r["cash"]) if (r.get("pos_cost") is not None and r.get("cash") is not None) else None
        pts.append({"ts": r["ts"], "assets_total": r["total"], "cost_line": cost_line,
                    "cash": r["cash"], "total_value": r["pos_value"]})
    if since:
        pts = [p for p in pts if p["ts"] >= since]
    return {"ok": True, "range": rng, "points": pts, "deposits": [], "note": ""}


def _shadow_stats():
    """shadow 专属统计 (战绩/全部条目/候选处理审计/事件流) — /api/shadow/monitor。"""
    from modules import auto_shadow as sh
    from modules.db import get_conn
    sh._ensure_tables()
    rows = sh._db_rows("SELECT * FROM shadow_positions ORDER BY id DESC LIMIT 150")
    n_open = sum(1 for r in rows if r["status"] == "open")
    n_pending = sum(1 for r in rows if r["status"] == "pending")
    n_stopped = sum(1 for r in rows if r["status"] == "stopped")
    resolved = [r for r in rows if r["status"] == "resolved"]
    n_won = sum(1 for r in resolved if (r["final_outcome"] or 0) == 1)
    realized = sum((r["realized_pnl_usd"] or 0) for r in rows if r["status"] in ("stopped", "resolved"))
    entries = []
    for r in rows:
        entries.append({
            "t": (r["created_at"] or "")[5:16], "title": (r["title"] or r["market_slug"] or "")[:60],
            "side": (r["side"] or "").upper(), "entry": r["entry_price"], "stop": r["stop_price"],
            "usd": r["stake_usd"], "status": r["status"], "dry": r.get("dry") or 0,
            "pnl": r["realized_pnl_usd"], "exit_reason": (r["exit_reason"] or "")[:40],
            "won": (r["final_outcome"] or 0) == 1 if r["status"] == "resolved" else None,
        })
    audit = [{"cand_id": a["cand_id"], "t": (a["ts"] or "")[5:16], "result": (a["result"] or "")[:80]}
             for a in sh._db_rows("SELECT * FROM shadow_done ORDER BY ts DESC LIMIT 40")]
    conn = get_conn()
    ev = [dict(x) for x in conn.execute(
        "SELECT timestamp, event_type, market_slug, detail FROM events "
        "WHERE event_type LIKE 'shadow%' ORDER BY id DESC LIMIT 30")]
    conn.close()
    events = [{"t": (e["timestamp"] or "")[5:16], "type": e["event_type"],
               "title": (e["market_slug"] or "")[:46], "detail": (e["detail"] or "")[:120]} for e in ev]
    try:
        from modules.version import VERSION
    except Exception:
        VERSION = ""
    return {"ok": True, "version": VERSION, "dry_mode": sh.DRY_RUN, "active": sh._thread_started,
            "last_tick": sh._state_get("last_tick"), "start_at": sh._state_get("start_at"),
            "n_total": len(rows), "n_open": n_open, "n_pending": n_pending,
            "n_stopped": n_stopped, "n_resolved": len(resolved), "n_won": n_won,
            "realized": round(realized, 2), "entries": entries, "audit": audit, "events": events,
            "rules": (f"${sh.STAKE_USD:g}/仓 · 只买≤{sh.MAX_PRICE:g} · 止损 入场-{int(sh.STOP_PCT*100)}%"
                      f"+${sh.FLOOR:.2f}地板 · 不止盈不重评 · 拿到结算")}


def register_routes(app):
    from flask import jsonify, request

    @app.route("/shadow")
    def shadow_page():
        return SHADOW_HTML

    @app.route("/api/shadow/holdings")
    def shadow_holdings_api():
        try:
            return jsonify(_build_holdings())
        except Exception as e:
            log.exception("/api/shadow/holdings failed")
            return jsonify({"ok": False, "message": str(e), "positions": [], "total_pnl": 0,
                            "total_cost": 0, "total_value": 0, "cash": 0, "assets_total": 0,
                            "position_count": 0})

    @app.route("/api/shadow/history")
    def shadow_history_api():
        rng = (request.args.get("range") or "1w").lower()
        try:
            return jsonify(_history(rng))
        except Exception as e:
            return jsonify({"ok": False, "message": str(e), "points": [], "deposits": [], "note": ""})

    @app.route("/api/shadow/monitor")
    def shadow_monitor_api():
        try:
            return jsonify(_shadow_stats())
        except Exception as e:
            log.exception("/api/shadow/monitor failed")
            return jsonify({"ok": False, "message": str(e), "entries": [], "audit": [], "events": []})

    return shadow_page


# ============================================================================
# 页面 — 导航/磁贴/资产曲线/当前持仓 = 逐段照搬 bench 克隆模板 (只换接口和文案);
#        shadow 专属区(战绩磁贴/全部条目/候选审计/事件流)用同款卡片。
# ============================================================================
SHADOW_HTML = r"""<!DOCTYPE html>
<html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>🟣 三号账户 · 低价拿到底</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🟣</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
:root{--bg:#0a0a14;--sf0:#0f0f1c;--sf:#16162a;--sf2:#1c1c36;--sf3:#23234a;--bd:rgba(255,255,255,0.06);--bd2:rgba(255,255,255,0.10);--tx:#e8e8ff;--tx2:#9898c8;--tx3:#6868b0;--ac:#00e5a0;--ac2:#00c8ff;--rd:#ff4070;--am:#ffc040;--vi:#8060ff;--acd:rgba(0,229,160,0.10);--rdd:rgba(255,64,112,0.10)}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--tx);min-height:100vh;background-image:radial-gradient(ellipse 1400px 700px at 50% -10%,rgba(0,200,255,0.05),transparent 65%),radial-gradient(ellipse 800px 500px at 90% 100%,rgba(128,96,255,0.04),transparent 60%);background-attachment:fixed;position:relative}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(255,255,255,0.012) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.012) 1px,transparent 1px);background-size:32px 32px;pointer-events:none;z-index:0}
nav{background:rgba(10,10,20,0.72);backdrop-filter:blur(28px) saturate(180%);-webkit-backdrop-filter:blur(28px) saturate(180%);border-bottom:1px solid var(--bd);padding:0 24px;height:56px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:100;flex-wrap:wrap}
.logo{width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#8060ff,#00c8ff);display:flex;align-items:center;justify-content:center;font-weight:700;color:#060610;font-size:15px}
.nt{font-size:14px;font-weight:600}.nt span{color:var(--tx3);font-weight:400;margin-left:8px;font-size:12px;font-family:'JetBrains Mono'}
.dino-track{position:relative;flex:1;height:34px;margin-right:24px;min-width:280px;overflow:hidden;user-select:none}
@media(max-width:900px){.dino-track{display:none}}
.dino-track .ground{position:absolute;bottom:7px;left:0;right:0;height:1px;background:var(--tx3);opacity:0.55}
.dino-track .cactus{position:absolute;bottom:8px;line-height:1;animation:cactus-roll 4.5s linear infinite;will-change:left}
.dino-track .c1{animation-delay:0s;font-size:14px}
.dino-track .c2{animation-delay:-1.5s;font-size:11px}
.dino-track .c3{animation-delay:-3.0s;font-size:13px}
@keyframes cactus-roll{0%{left:calc(100% + 4px)}100%{left:-22px}}
.dino-track .dino{position:absolute;bottom:7px;line-height:1;will-change:transform;animation:dino-jump 4.5s cubic-bezier(0.45,0,0.55,1) infinite}
.dino-track .d1{left:6px;font-size:18px}
.dino-track .d2{left:26px;font-size:13px}
.dino-track .d3{left:42px;font-size:15px}
@keyframes dino-jump{
  0%,18%,30%,52%,64%,86%,98%,100%{transform:scaleX(-1) translateY(0)}
  20%,28%{transform:scaleX(-1) translateY(-15px)}
  54%,62%{transform:scaleX(-1) translateY(-15px)}
  88%,96%{transform:scaleX(-1) translateY(-15px)}
}
.pages-tab{display:flex;gap:6px;margin-left:8px}
.ptab{font-size:11px;font-weight:500;padding:6px 12px;background:transparent;color:var(--tx3);border:1px solid var(--bd);border-radius:8px;cursor:pointer;text-decoration:none;transition:all .15s;white-space:nowrap}
.ptab:hover{color:var(--tx);border-color:var(--bd2);background:var(--sf)}
.ptab-active{background:var(--acd);color:var(--ac);border-color:rgba(0,229,160,0.35);font-weight:600}
.nr{margin-left:auto;display:flex;align-items:center;gap:12px}
.lp{display:flex;align-items:center;gap:5px;padding:4px 12px;background:var(--acd);border:1px solid rgba(0,229,160,0.2);border-radius:20px;font-size:10px;font-weight:600;color:var(--ac)}
.ld{width:5px;height:5px;border-radius:50%;background:var(--ac);animation:p 2s ease-in-out infinite}
@keyframes p{0%,100%{opacity:1}50%{opacity:.3}}
.wrap{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:20px 20px 60px}
.sl{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:var(--tx2);margin:26px 0 12px 2px;position:relative;padding-left:12px;display:flex;align-items:center;gap:10px}
.sl::before{content:'';position:absolute;left:0;top:50%;transform:translateY(-50%);width:3px;height:14px;background:linear-gradient(180deg,var(--ac2),var(--vi));border-radius:2px}
.sl .cnt{font-size:9px;letter-spacing:0;text-transform:none;font-weight:600}
.ms{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
@media(max-width:900px){.ms{grid-template-columns:repeat(2,1fr)}}
.m{background:linear-gradient(180deg,var(--sf) 0%,var(--sf2) 100%);border:1px solid var(--bd);border-radius:14px;padding:16px 18px;position:relative;overflow:hidden;transition:transform .2s,border-color .2s,box-shadow .2s}
.m:hover{transform:translateY(-2px);border-color:var(--bd2);box-shadow:0 8px 24px rgba(0,0,0,0.3)}
.m::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.m.g::before{background:linear-gradient(90deg,#00e5a0,#00c8ff)}.m.r::before{background:linear-gradient(90deg,#ff4070,#ff8060)}.m.b::before{background:linear-gradient(90deg,#00c8ff,#8060ff)}.m.v::before{background:linear-gradient(90deg,#8060ff,#c060ff)}
.mi{font-size:16px;margin-bottom:8px}.ml{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--tx3);margin-bottom:6px}
.mv{font-size:24px;font-weight:700;font-family:'JetBrains Mono';letter-spacing:-1px}
.msb{font-size:10px;color:var(--tx3);margin-top:6px}
.op-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.opbtn{padding:7px 15px;border-radius:9px;border:1px solid var(--bd);background:var(--sf2);color:var(--tx2);font-family:'Space Grotesk';font-size:11.5px;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap}
.opbtn:hover{transform:translateY(-1px);filter:brightness(1.12)}
.upd{font-size:10px;color:var(--tx3);font-family:'JetBrains Mono'}
.card{background:linear-gradient(180deg,var(--sf) 0%,var(--sf2) 100%);border:1px solid var(--bd);border-radius:14px;overflow:hidden;margin-bottom:16px;transition:border-color .2s,box-shadow .2s}
.card:hover{border-color:var(--bd2)}
.chd{padding:14px 18px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.chd h2{font-size:12px;font-weight:600;color:var(--tx2)}
.cnt{font-size:9px;padding:3px 8px;border-radius:8px;font-weight:600;font-family:'JetBrains Mono';background:var(--acd);color:var(--ac)}
.cnt.dimc{background:var(--sf);color:var(--tx3);font-weight:500}
.cb{max-height:520px;overflow-y:auto;scrollbar-width:thin;padding:4px 0}
.cb::-webkit-scrollbar{width:4px}.cb::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:2px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}
.range-btn{padding:4px 10px;border:1px solid var(--bd);background:transparent;color:var(--tx3);border-radius:6px;cursor:pointer;font-size:11px;font-family:'JetBrains Mono';letter-spacing:.5px}
.range-btn:hover{border-color:var(--ac2);color:var(--ac2)}
.range-btn.active{background:rgba(0,200,255,0.1);border-color:#00c8ff;color:#00c8ff}
#portfolio-canvas{display:block;width:100%!important;height:100%!important}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{padding:9px 16px;text-align:left;vertical-align:middle;border-bottom:1px solid var(--bd)}
tr:last-child td{border-bottom:none}
th{color:var(--tx3);font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.6px}
tbody tr:hover{background:linear-gradient(90deg,rgba(0,200,255,0.05),transparent 80%)}
.mono{font-family:'JetBrains Mono';font-size:11.5px}
.dim{color:var(--tx3)}.subn{color:var(--tx3);font-size:10.5px;font-family:'JetBrains Mono'}
.g{color:var(--ac)}.a{color:var(--am)}.r{color:var(--rd)}.b{color:var(--ac2)}.vi{color:var(--vi)}
.side{display:inline-block;min-width:34px;text-align:center;border-radius:6px;padding:2px 7px;font-size:10.5px;font-weight:700;font-family:'JetBrains Mono'}
.side.YES{background:rgba(0,229,160,.14);color:var(--ac);border:1px solid rgba(0,229,160,.35)}
.side.NO{background:rgba(255,64,112,.14);color:var(--rd);border:1px solid rgba(255,64,112,.35)}
.empty{color:var(--tx3);font-size:12px;padding:16px 18px;text-align:center}
.st{font-size:10.5px;font-weight:600;white-space:nowrap}
/* 当前持仓面板 — 照搬主页 #pos-panel-current (去掉"操作"列, chips 列 = q·信心·止损线) */
#pos-panel-current .pos-hdr,#pos-panel-current .pos-row{display:grid;grid-template-columns:minmax(190px,2.4fr) 48px 62px 66px 66px 52px 82px 72px 90px 210px;gap:5px;align-items:center;padding:13px 18px;border-bottom:1px solid var(--bd);font-size:12px}
#pos-panel-current .pos-hdr{font-weight:700;color:var(--tx3);font-size:10px;background:var(--sf2);text-transform:uppercase;letter-spacing:.4px;position:sticky;top:0;z-index:1}
#pos-panel-current .pos-row:hover{background:linear-gradient(90deg,rgba(0,200,255,0.05),transparent 80%)}
#pos-panel-current .pos-row .nm{font-weight:600;white-space:normal;word-break:break-word;line-height:1.35;padding-right:6px;font-size:13.5px}
#pos-panel-current .pos-row .mono{font-family:'JetBrains Mono';font-size:12px}
#pos-panel-current .pos-row .cur-value{font-size:15px;font-weight:700}
#pos-panel-current .pos-row .cur-pnl,#pos-panel-current .pos-row .cur-pnl-d{font-size:16.5px;font-weight:800}
#pos-panel-current .vchip{font-size:11px;font-weight:700;padding:3px 9px;border-radius:7px;background:var(--sf);border:1px solid var(--bd);color:var(--tx2);white-space:nowrap}
#pos-panel-current .vchip-q{background:rgba(0,200,255,0.14);color:#00c8ff;border-color:rgba(0,200,255,0.42)}
#pos-panel-current .vchip-conf{background:rgba(255,192,64,0.14);color:#ffc040;border-color:rgba(255,192,64,0.42)}
#pos-panel-current .vchip-stop{background:rgba(255,64,112,0.12);color:#ff6d90;border-color:rgba(255,64,112,0.4)}
</style></head><body>
<nav>
<div class="logo">🟣</div>
<div class="nt">三号账户 · 低价拿到底 <span id="rules"></span></div>
<div class="pages-tab">
<a class="ptab" href="/">🏠 监控</a>
<a class="ptab" href="/bench">🧪 Bench基准</a>
<a class="ptab ptab-active" href="/shadow">🟣 三号低价</a>
<a class="ptab" href="/history">📊 往期仓位</a>
<a class="ptab" href="/paper">🧪 测试仓</a>
<a class="ptab" href="/m">📱 手机版</a>
</div>
<div class="dino-track" title="Chrome 离线小恐龙 — 恐龙家族躲仙人掌"><span class="ground"></span><span class="cactus c1">🌵</span><span class="cactus c2">🌵</span><span class="cactus c3">🌵</span><span class="dino d1">🦖</span><span class="dino d2">🦕</span><span class="dino d3">🦖</span></div>
<div class="nr"><div class="lp"><div class="ld"></div><span id="mode-pill">监控中 · 30s</span></div></div>
</nav>
<div class="wrap">

<div class="ms">
<div class="m g"><div class="mi">💰</div><div class="ml">总盈亏</div><div class="mv" id="m-pnl">—</div><div class="msb">所有持仓浮盈亏</div></div>
<div class="m b"><div class="mi">📦</div><div class="ml">持仓数</div><div class="mv" id="m-cnt">—</div><div class="msb">三号真仓</div></div>
<div class="m v"><div class="mi">💵</div><div class="ml">现金</div><div class="mv" id="m-cash" style="color:var(--am)">—</div><div class="msb">可用余额</div></div>
<div class="m b"><div class="mi">💼</div><div class="ml">总资产</div><div class="mv" id="m-assets" style="color:var(--ac2)">—</div><div class="msb">持仓市值 + 现金</div></div>
</div>
<div class="ms">
<div class="m v"><div class="mi">🏁</div><div class="ml">已结算战绩</div><div class="mv" id="m-res">—</div><div class="msb" id="m-res-sub">赢 — / 结算 —</div></div>
<div class="m g"><div class="mi">🏦</div><div class="ml">落袋盈亏</div><div class="mv" id="m-real">—</div><div class="msb">止损+结算的合计</div></div>
<div class="m r"><div class="mi">🔻</div><div class="ml">-60% 止损数</div><div class="mv" id="m-stopped">—</div><div class="msb">唯一的卖出方式</div></div>
<div class="m b"><div class="mi">📒</div><div class="ml">总条目</div><div class="mv" id="m-total">—</div><div class="msb" id="m-mode">$2/仓 · 拿到结算</div></div>
</div>
<div class="op-row">
<button class="opbtn" onclick="trigger('/api/shadow/scan_now')">▶ 立即扫描候选</button>
<span class="upd" id="upd"></span>
</div>

<div class="sl">📈 资产总值曲线</div>
<div class="card" style="padding:18px">
<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;gap:12px;flex-wrap:wrap">
<div style="flex:1;min-width:220px">
<div id="chart-delta" style="font-size:26px;font-weight:700;font-family:'JetBrains Mono';color:var(--ac2);letter-spacing:-.5px;line-height:1.1">$0.00</div>
<div id="chart-delta-label" style="font-size:10px;color:var(--tx2);margin-top:3px">区间涨跌 = 末点资产 − 起点资产</div>
</div>
<div style="display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end">
<button class="range-btn" data-range="1d" onclick="loadChart('1d')">1D</button>
<button class="range-btn active" data-range="1w" onclick="loadChart('1w')">1W</button>
<button class="range-btn" data-range="1m" onclick="loadChart('1m')">1M</button>
<button class="range-btn" data-range="1y" onclick="loadChart('1y')">1Y</button>
<button class="range-btn" data-range="all" onclick="loadChart('all')">ALL</button>
</div>
</div>
<div style="position:relative;height:280px"><canvas id="portfolio-canvas"></canvas></div>
</div>

<div class="sl">📦 当前持仓 <span class="cnt dimc" id="pos-cnt"></span></div>
<div class="card"><div id="pos-panel-current" class="cb">
<div class="pos-hdr"><span>名称</span><span>方向</span><span>距结算</span><span>入场价</span><span>当前价</span><span>份数</span><span>当前价值</span><span>盈亏%</span><span>盈亏$</span><span>q · 信心 · 止损线</span></div>
<div id="holdings"><div class="empty">加载中…</div></div>
</div></div>

<div class="grid2">
  <div class="card"><div class="chd"><h2>🗂 候选处理审计 (买/跳过都点名)</h2><span class="cnt dimc" id="aud-n">—</span></div>
    <div class="cb"><table><tbody id="tb-aud"></tbody></table></div></div>
  <div class="card"><div class="chd"><h2>⚡ 三号账户事件流</h2><span class="cnt dimc">买入/止损/结算</span></div>
    <div class="cb"><table><tbody id="tb-ev"></tbody></table></div></div>
</div>

<div class="sl">📒 全部条目 (买入→止损/拿到结算) <span class="cnt dimc" id="ent-n"></span></div>
<div class="card"><div class="cb"><table><thead><tr><th>时间</th><th>市场</th><th>方向</th><th>入场</th><th>止损线</th><th>金额</th><th>状态</th><th>结局</th></tr></thead><tbody id="tb-ent"></tbody></table></div></div>

</div>
<script>
var CUR_RANGE='1w', portfolioChart=null;
var RANGE_LABELS={'1d':'今日','1w':'近一周','1m':'近一月','1y':'近一年','all':'全部'};
function esc(s){return (s==null?'':(''+s)).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function usd(n){n=+n||0;return (n<0?'-$':'$')+Math.abs(n).toFixed(2)}
var CONF_CN={high:'高',medium:'中',low:'低'};
var ST={open:'<span class="st g">🟢持有中</span>',stopped:'<span class="st r">🔻止损卖</span>',resolved:'<span class="st b">🏁已结算</span>',pending:'<span class="st a">⏳下单中</span>'};
function stBadge(s){if(!s)return '—';var k=(''+s).split(':')[0];return ST[k]||('<span class="st r">'+esc((''+s).slice(0,18))+'</span>')}
async function trigger(u){try{var r=await fetch(u,{method:'POST'});var d=await r.json();alert(d.message||'ok')}catch(e){alert('失败: '+e)}}

/* ===== 指标磁贴 + 当前持仓 (照搬主页 renderMetrics/renderHoldings, 数据换 /api/shadow/holdings) ===== */
function renderMetrics(s){
  if(!s||!s.ok)return;
  var pnl=document.getElementById('m-pnl');
  pnl.textContent=usd(s.total_pnl); pnl.style.color=(+s.total_pnl>=0)?'var(--ac)':'var(--rd)';
  document.getElementById('m-cnt').textContent=s.position_count!=null?s.position_count:'—';
  document.getElementById('m-cash').textContent=usd(s.cash);
  document.getElementById('m-assets').textContent=usd(s.assets_total);
}
function renderHoldings(s){
  var box=document.getElementById('holdings');
  if(!s||!s.ok||!s.positions){box.innerHTML='<div class="empty">读取失败</div>';return}
  document.getElementById('pos-cnt').textContent=s.positions.length+' 仓';
  if(!s.positions.length){box.innerHTML='<div class="empty">暂无持仓 — 下一个扫描点 (09:00/21:00) 出低价推荐就买</div>';return}
  var h='';
  s.positions.forEach(function(p){
    var pd=+p.pnl_dollar||0, pp=+p.pnl_pct||0, gd=pd>=0, gp=pp>=0;
    var pdc=gd?'#00e5a0':'#ff4070', ppc=gp?'#00e5a0':'#ff4070';
    var days=(p.days_left==null)?'—':(p.days_left+'天');
    var qc=(p.q!=null)?'<span class="vchip vchip-q">q '+Math.round(p.q*100)+'%</span>':'<span class="vchip" style="opacity:.45">q —</span>';
    var cc=p.confidence?'<span class="vchip vchip-conf">信心'+(CONF_CN[p.confidence]||p.confidence)+'</span>':'';
    var sc=(p.stop_price!=null)?'<span class="vchip vchip-stop">止损$'+(+p.stop_price).toFixed(2)+'</span>':'';
    h+='<div class="pos-row">'+
      '<span class="nm">'+esc(p.title||p.asset)+'</span>'+
      '<span class="mono" style="color:'+(p.side==='YES'?'#00a884':'#cc3050')+';font-weight:600">'+esc(p.side)+'</span>'+
      '<span class="mono" style="color:var(--tx3)">'+days+'</span>'+
      '<span class="mono" style="color:#8060ff">$'+(+p.avg_price).toFixed(3)+'</span>'+
      '<span class="mono" style="color:#00c8ff">$'+(+p.cur_price).toFixed(3)+'</span>'+
      '<span class="mono" style="color:#ffc040">'+(+p.size).toFixed(1)+'</span>'+
      '<span class="mono cur-value" style="color:'+pdc+'">$'+(+p.value).toFixed(2)+'</span>'+
      '<span class="mono cur-pnl" style="color:'+ppc+'">'+(gp?'+':'')+pp.toFixed(1)+'%</span>'+
      '<span class="mono cur-pnl-d" style="color:'+pdc+'">'+(gd?'+$':'-$')+Math.abs(pd).toFixed(2)+'</span>'+
      '<span style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">'+qc+cc+sc+'</span>'+
      '</div>';
  });
  box.innerHTML=h;
}

/* ===== 资产曲线 (照搬主页 loadChart/setChartDelta, 数据换 /api/shadow/history) ===== */
var CHART_NOTE='';
function setChartDelta(idx){
  var dEl=document.getElementById('chart-delta'),lEl=document.getElementById('chart-delta-label');
  var pts=portfolioChart?portfolioChart.data.datasets[0].data:[];
  if(!pts||!pts.length){dEl.textContent='$0.00';dEl.style.color='var(--tx3)';lEl.textContent=RANGE_LABELS[CUR_RANGE]||'';return}
  var t=(idx==null)?pts.length-1:idx,delta=pts[t].y-pts[0].y;
  dEl.textContent=(delta>=0?'+$':'-$')+Math.abs(delta).toFixed(2);
  dEl.style.color=delta>=0?'var(--ac)':'var(--rd)';
  lEl.textContent=(RANGE_LABELS[CUR_RANGE]||'')+' · 起 '+usd(pts[0].y)+' → 现 '+usd(pts[t].y)+(CHART_NOTE?' · '+CHART_NOTE:'');
}
async function loadChart(range){
  CUR_RANGE=range;
  document.querySelectorAll('.range-btn[data-range]').forEach(function(b){b.classList.toggle('active',b.dataset.range===range)});
  try{
    var d=await fetch('/api/shadow/history?range='+range).then(r=>r.json());
    if(!d.ok)return;
    var pts=d.points||[];
    CHART_NOTE=d.note||'';
    var valuePts=pts.map(function(p){return {x:p.ts*1000,y:p.assets_total}});
    var costPts=pts.map(function(p){return {x:p.ts*1000,y:(p.cost_line!=null)?p.cost_line:null}});
    if(portfolioChart){portfolioChart.data.datasets[0].data=valuePts;portfolioChart.data.datasets[1].data=costPts;portfolioChart.update('none');setChartDelta(null);return}
    if(typeof Chart==='undefined'){document.getElementById('chart-delta-label').textContent='(Chart.js 未加载, 检查网络)';return}
    var ctx=document.getElementById('portfolio-canvas').getContext('2d');
    var gP=ctx.createLinearGradient(0,0,0,280);gP.addColorStop(0,'rgba(0,229,160,0.34)');gP.addColorStop(1,'rgba(0,229,160,0.02)');
    var gL=ctx.createLinearGradient(0,0,0,280);gL.addColorStop(0,'rgba(255,64,112,0.03)');gL.addColorStop(1,'rgba(255,64,112,0.30)');
    portfolioChart=new Chart(ctx,{type:'line',data:{datasets:[
      {label:'资产总值',data:valuePts,borderColor:'#22d3ee',fill:{target:1,above:gP,below:gL},tension:0.35,pointRadius:0,pointHoverRadius:5,borderWidth:2.5},
      {label:'成本线',data:costPts,borderColor:'rgba(150,150,190,0.55)',borderDash:[5,4],borderWidth:1.3,fill:false,tension:0.35,pointRadius:0,pointHoverRadius:0}
    ]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      onHover:function(e,active){var v=active.find(function(a){return a.datasetIndex===0});setChartDelta(v?v.index:null)},
      plugins:{legend:{display:true,labels:{color:'#8888c0',font:{size:10},usePointStyle:true,boxWidth:8,padding:12}},
        tooltip:{backgroundColor:'rgba(17,17,40,0.95)',borderColor:'#1e1e4a',borderWidth:1,titleColor:'#e8e8ff',bodyColor:'#cfeef8',padding:10,filter:function(i){return i.parsed.y!=null},
          callbacks:{title:function(items){return new Date(items[0].parsed.x).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})},
            label:function(item){return (item.datasetIndex===0?'资产总值: ':'成本线: ')+'$'+item.parsed.y.toFixed(2)}}}},
      scales:{x:{type:'time',ticks:{color:'#5858a0',font:{size:10},maxRotation:0,autoSkipPadding:20},grid:{color:'rgba(255,255,255,0.04)'}},
        y:{ticks:{color:'#5858a0',font:{size:10},callback:function(v){return '$'+v.toFixed(0)}},grid:{color:'rgba(255,255,255,0.04)'}}}}});
    document.getElementById('portfolio-canvas').addEventListener('mouseleave',function(){setChartDelta(null)});
    setChartDelta(null);
  }catch(e){console.error('chart load failed',e)}
}

/* ===== shadow 专属: 战绩磁贴 / 全部条目 / 候选审计 / 事件流 ===== */
function renderShadow(d){
  if(!d||!d.ok)return;
  document.getElementById('rules').textContent=d.rules||'';
  document.getElementById('mode-pill').textContent=(d.dry_mode?'DRY 空跑':(d.active?'监控中 · 30s':'⚠️ 未激活'));
  document.getElementById('m-res').textContent=d.n_resolved?((d.n_won/d.n_resolved*100).toFixed(0)+'%'):'—';
  document.getElementById('m-res-sub').textContent='赢 '+d.n_won+' / 结算 '+d.n_resolved;
  var re=document.getElementById('m-real');re.textContent=usd(d.realized);re.style.color=(+d.realized>=0)?'var(--ac)':'var(--rd)';
  document.getElementById('m-stopped').textContent=d.n_stopped;
  document.getElementById('m-total').textContent=d.n_total;
  document.getElementById('tb-ent').innerHTML=(d.entries||[]).map(function(e){
    var outc;
    if(e.status==='resolved'){outc=e.won?'<span class="g">🏆 赢→$1</span>':'<span class="r">💀 输→$0</span>'}
    else if(e.status==='stopped'){outc='<span class="r">'+esc(e.exit_reason||'止损')+'</span>'}
    else{outc='<span class="dim">⏳拿到结算</span>'}
    return '<tr><td class="mono dim">'+esc(e.t)+'</td><td>'+esc(e.title)+(e.dry?' <span class="a">🧪dry</span>':'')+'</td>'+
     '<td><span class="side '+e.side+'">'+e.side+'</span></td>'+
     '<td class="mono">'+(e.entry!=null?(+e.entry).toFixed(3):'—')+'</td>'+
     '<td class="mono r">'+(e.stop!=null?(+e.stop).toFixed(3):'—')+'</td>'+
     '<td class="mono">'+(e.usd!=null?usd(e.usd):'—')+'</td><td>'+stBadge(e.status)+'</td>'+
     '<td>'+outc+(e.pnl!=null?' <span class="mono" style="color:'+((+e.pnl>=0)?'var(--ac)':'var(--rd)')+'">'+usd(e.pnl)+'</span>':'')+'</td></tr>'}).join('')
    ||'<tr><td colspan="8" class="empty">空 — 下一个扫描点 (09:00/21:00) 出低价推荐就买</td></tr>';
  document.getElementById('ent-n').textContent=d.n_total+' 条';
  document.getElementById('tb-aud').innerHTML=(d.audit||[]).map(function(a){
    var cls=(a.result||'').indexOf('bought')===0?'g':((a.result||'').indexOf('error')===0?'r':'dim');
    return '<tr><td class="mono dim" style="width:90px">'+esc(a.t)+'</td><td class="mono dim" style="width:70px">#'+esc(a.cand_id)+'</td><td class="'+cls+'" style="font-size:11px">'+esc(a.result)+'</td></tr>'}).join('')
    ||'<tr><td class="empty">还没处理过候选</td></tr>';
  document.getElementById('aud-n').textContent=(d.audit||[]).length+' 条';
  document.getElementById('tb-ev').innerHTML=(d.events||[]).map(function(e){
    return '<tr><td class="mono dim" style="width:90px">'+esc(e.t)+'</td><td style="width:110px" class="vi">'+esc(e.type)+'</td>'+
     '<td>'+esc(e.title)+'<div class="dim" style="font-size:10.5px">'+esc(e.detail)+'</div></td></tr>'}).join('')
    ||'<tr><td class="empty">暂无三号账户事件</td></tr>';
}

async function loadAll(){
  try{
    var h=await fetch('/api/shadow/holdings').then(function(r){return r.json()});
    renderMetrics(h);renderHoldings(h);
    var b=await fetch('/api/shadow/monitor').then(function(r){return r.json()});
    renderShadow(b);
    document.getElementById('upd').textContent='更新于 '+new Date().toLocaleTimeString();
  }catch(e){document.getElementById('upd').textContent='加载失败: '+e.message}
}
loadAll();loadChart('1w');
setInterval(loadAll,30000);
setInterval(function(){loadChart(CUR_RANGE)},120000);
</script></body></html>"""
