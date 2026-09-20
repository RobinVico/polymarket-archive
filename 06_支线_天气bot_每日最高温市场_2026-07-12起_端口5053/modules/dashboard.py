"""天气 bot 仪表盘 (Flask, 127.0.0.1:5053) — 深色风格, 今日计划 / 持仓 / 历史 / 日志.
只读为主 + 两个开关: 紧急停止 (kv halt) / 紧急卖出 (真钱仓兜底用).
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request

from modules import config, db
from modules.version import VERSION

log = logging.getLogger("dashboard")
TZ = timezone(timedelta(hours=config.TZ_OFFSET_H))

_cash_cache = [0.0, None]  # [ts, value]


def _fmt_local(iso_s):
    if not iso_s:
        return "—"
    try:
        return datetime.fromisoformat(iso_s).astimezone(TZ).strftime("%H:%M")
    except ValueError:
        return "—"


def _status_cn(plan, now_ts):
    st = plan["status"]
    if st == "watching":
        try:
            fire = datetime.fromisoformat(plan["fire_utc"]).timestamp()
        except (ValueError, TypeError):
            fire = 0
        return "⏳ 等日落" if now_ts < fire else "🎯 盯条件中"
    return {
        "ordered": "✅ 已下单", "would_buy": "📝 该买(未真下)", "skipped": "⏭️ 跳过",
        "won": "🟢 赢", "lost": "🔴 输", "void": "⚪ 无效", "sold_early": "🚪 提前卖出",
    }.get(st, st)


def create_app(trader, state):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return HTML.replace("__VERSION__", VERSION)

    @app.route("/api/state")
    def api_state():
        now = datetime.now(timezone.utc)
        today = datetime.now(TZ).date()
        today_str = str(today)

        rows = []
        for p in db.plans_for_date(today_str):
            cfg = config.CITIES.get(p["city"], {})
            rows.append({
                "city": cfg.get("name", p["city"]),
                "sunset": _fmt_local(p["sunset_utc"]),
                "status": p["status"],
                "status_cn": _status_cn(p, now.timestamp()),
                "day_max": p["day_max"], "cur_temp": p["cur_temp"],
                "bucket_label": p["bucket_label"] or "—",
                "best_ask": p["best_ask"],
                "reason": p["reason"] or "",
                "breached": bool(p["breached"]),
                "mode": p["mode"], "plan_id": p["id"],
            })

        hist_rows = []
        for p in db.recent_plans(40):
            cfg = config.CITIES.get(p["city"], {})
            hist_rows.append({
                "date": p["local_date"], "city": cfg.get("name", p["city"]),
                "bucket_label": p["bucket_label"] or "—",
                "status": p["status"], "status_cn": _status_cn(p, now.timestamp()),
                "best_ask": p["best_ask"], "mode": p["mode"],
                "winning_label": p["winning_label"] or "",
                "pnl": p["pnl"], "reason": (p["reason"] or "")[:120],
            })

        cash = None
        if trader.ready and time.time() - _cash_cache[0] > 60:
            _cash_cache[0] = time.time()
            _cash_cache[1] = trader.get_cash_balance()
        if trader.ready:
            cash = _cash_cache[1]

        funder = os.getenv("POLY_FUNDER", "").strip()
        mode = "PAPER" if config.PAPER else ("real" if trader.ready else "no_wallet")

        log_tail = []
        try:
            lp = os.path.join(config.ROOT, "bot.log")
            if os.path.exists(lp):
                with open(lp, "r", encoding="utf-8", errors="replace") as f:
                    log_tail = f.readlines()[-60:]
        except OSError:
            pass

        return jsonify({
            "version": VERSION,
            "now_local": datetime.now(TZ).strftime("%m-%d %H:%M:%S"),
            "mode": mode,
            "wallet": {"ready": trader.ready, "err": trader.err, "cash": cash,
                       "funder": (funder[:6] + "…" + funder[-4:]) if funder else ""},
            "halt": db.kv_get("halt", "0") == "1",
            "alerts": db.get_alerts(),
            "today": rows,
            "positions": trader.get_positions() if trader.ready else [],
            "summary": db.stats_summary(),
            "history": hist_rows,
            "params": {"order_usd": config.ORDER_USD, "daily_cap": config.DAILY_CAP_USD,
                       "price_min": config.PRICE_MIN, "price_max": config.PRICE_MAX,
                       "temp_margin": config.TEMP_MARGIN_C, "fee_bps": config.FEE_RATE_BPS},
            "log_tail": log_tail,
        })

    @app.route("/api/halt", methods=["POST"])
    def api_halt():
        on = bool((request.get_json(silent=True) or {}).get("on"))
        db.kv_set("halt", "1" if on else "0")
        log.warning(f"紧急停止开关 → {'开' if on else '关'}")
        return jsonify({"ok": True, "halt": on})

    @app.route("/api/alerts/clear", methods=["POST"])
    def api_alerts_clear():
        db.clear_alerts()
        return jsonify({"ok": True})

    @app.route("/api/sell", methods=["POST"])
    def api_sell():
        pid = (request.get_json(silent=True) or {}).get("plan_id")
        plans = [p for p in db.recent_plans(200) if p["id"] == pid]
        if not plans:
            return jsonify({"ok": False, "msg": "找不到该计划"})
        p = plans[0]
        if p["status"] != "ordered" or p["mode"] != "real":
            return jsonify({"ok": False, "msg": "只有真钱已下单的仓位能紧急卖出"})
        if not trader.ready:
            return jsonify({"ok": False, "msg": "钱包未就绪"})
        ok, msg = trader.sell(p["token_id"], p["filled_shares"], reason="dashboard 紧急卖出")
        if ok:
            db.update_plan(p["id"], status="sold_early", reason=f"紧急卖出: {msg}",
                           resolved_at=db.utcnow_iso())
            db.add_alert(f"🚪 {p['city']} 紧急卖出: {msg}")
        return jsonify({"ok": ok, "msg": msg})

    return app


HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🌤️ 天气 bot</title>
<style>
:root{--bg:#0b0e14;--card:#12161f;--bd:#1f2633;--tx:#dbe2ee;--tx2:#8a94a6;--cy:#22d3ee;
--gn:#34d399;--rd:#f87171;--am:#fbbf24;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;padding:14px;max-width:1100px;margin:0 auto}
h1{font-size:19px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{font-size:11px;padding:2px 9px;border-radius:99px;border:1px solid var(--bd);color:var(--tx2)}
.badge.real{color:var(--gn);border-color:var(--gn)}
.badge.no_wallet{color:var(--am);border-color:var(--am)}
.badge.PAPER{color:var(--cy);border-color:var(--cy)}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:13px 15px;margin-top:13px}
.card h2{font-size:14px;color:var(--cy);margin-bottom:9px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{color:var(--tx2);text-align:left;font-weight:500;padding:4px 7px;border-bottom:1px solid var(--bd);white-space:nowrap}
td{padding:5px 7px;border-bottom:1px solid rgba(255,255,255,.04);vertical-align:top}
.muted{color:var(--tx2)}.gn{color:var(--gn)}.rd{color:var(--rd)}.am{color:var(--am)}.cy{color:var(--cy)}
.alerts{margin-top:13px}
.alert{background:rgba(248,113,113,.12);border:1px solid var(--rd);border-radius:9px;padding:8px 12px;margin-top:6px;font-size:12.5px;animation:fl 1.2s ease-in-out infinite alternate}
@keyframes fl{from{opacity:.75}to{opacity:1}}
button{background:none;border:1px solid var(--bd);color:var(--tx);border-radius:8px;padding:5px 12px;cursor:pointer;font-size:12px}
button:hover{border-color:var(--cy);color:var(--cy)}
button.danger{border-color:var(--rd);color:var(--rd)}
button.on{background:var(--rd);color:#fff;border-color:var(--rd)}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:9px}
.stat{background:rgba(255,255,255,.03);border:1px solid var(--bd);border-radius:10px;padding:7px 13px;font-size:12px;color:var(--tx2)}
.stat b{display:block;font-size:16px;color:var(--tx)}
pre{font:11px/1.5 "SF Mono",Menlo,monospace;color:var(--tx2);white-space:pre-wrap;word-break:break-all;max-height:280px;overflow-y:auto}
.reason{color:var(--tx2);font-size:11.5px;max-width:330px}
@media(max-width:700px){body{padding:8px}.reason{max-width:150px}}
</style>
</head>
<body>
<h1>🌤️ 天气 bot <span class="muted" style="font-size:12px">v__VERSION__</span>
  <span id="mode" class="badge">…</span>
  <span id="cash" class="badge"></span>
  <span id="clock" class="badge"></span>
  <button id="haltBtn" class="danger" onclick="haltToggle()">⛔ 紧急停止</button>
</h1>

<div id="alerts" class="alerts"></div>

<div class="card">
  <h2>📅 今日计划 <span class="muted" id="params"></span></h2>
  <table><thead><tr><th>城市</th><th>日落</th><th>状态</th><th>当日最高</th><th>现温</th><th>目标档</th><th>卖一价</th><th>说明</th></tr></thead>
  <tbody id="today"></tbody></table>
</div>

<div class="card">
  <h2>💼 钱包持仓</h2>
  <div id="walletmsg" class="muted" style="font-size:12.5px"></div>
  <table id="postable" style="display:none"><thead><tr><th>市场</th><th>方向</th><th>数量</th><th>均价</th><th>现价</th><th>盈亏%</th></tr></thead>
  <tbody id="positions"></tbody></table>
</div>

<div class="card">
  <h2>📊 历史成绩</h2>
  <div class="stats" id="sumstats"></div>
  <table><thead><tr><th>日期</th><th>城市</th><th>买的档</th><th>价</th><th>状态</th><th>结算档</th><th>盈亏$</th><th>说明</th></tr></thead>
  <tbody id="history"></tbody></table>
</div>

<div class="card"><h2>📜 日志 (最近60行)</h2><pre id="logs"></pre></div>

<script>
let HALT=false;
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function fmt(x,d){return x==null?'—':Number(x).toFixed(d==null?3:d)}
async function load(){
  try{
    const r=await fetch('/api/state');const s=await r.json();
    const modeTxt={real:'💰 真钱模式',no_wallet:'🕓 待钱包(只记录)',PAPER:'🧪 PAPER'}[s.mode]||s.mode;
    const m=document.getElementById('mode');m.textContent=modeTxt;m.className='badge '+s.mode;
    document.getElementById('clock').textContent='🕐 '+s.now_local;
    document.getElementById('cash').textContent=s.wallet.ready?('现金 $'+fmt(s.wallet.cash,2)+' · '+s.wallet.funder):'';
    HALT=s.halt;
    const hb=document.getElementById('haltBtn');
    hb.textContent=s.halt?'▶️ 已停止·点击恢复':'⛔ 紧急停止';hb.className=s.halt?'danger on':'danger';
    document.getElementById('params').textContent=` $${s.params.order_usd}/市场 · 日上限 $${s.params.daily_cap} · 买价 ${s.params.price_min}~${s.params.price_max} · 降温≥${s.params.temp_margin}°C · taker费${s.params.fee_bps/100}%`;
    document.getElementById('alerts').innerHTML=(s.alerts||[]).slice(-6).map(a=>
      `<div class="alert">${esc(a.msg)} <span class="muted">${esc((a.ts||'').slice(5,16))}</span></div>`).join('')
      +((s.alerts||[]).length?`<div style="margin-top:6px"><button onclick="clearAlerts()">知道了, 清除提醒</button></div>`:'');
    document.getElementById('today').innerHTML=(s.today||[]).map(p=>{
      const cls=p.status==='ordered'?'gn':(p.status==='would_buy'?'cy':(p.status==='skipped'?'muted':(p.breached?'rd':'')));
      return `<tr><td><b>${esc(p.city)}</b>${p.breached?' 🚨':''}</td><td>${esc(p.sunset)}</td>
      <td class="${cls}">${esc(p.status_cn)}</td><td>${p.day_max==null?'—':fmt(p.day_max,1)+'°'}</td>
      <td>${p.cur_temp==null?'—':fmt(p.cur_temp,1)+'°'}</td><td><b>${esc(p.bucket_label)}</b></td>
      <td>${p.best_ask==null?'—':fmt(p.best_ask,3)}</td><td class="reason">${esc(p.reason)}</td></tr>`;
    }).join('')||'<tr><td colspan="8" class="muted">今天还没有计划 (启动后 30 秒内生成)</td></tr>';
    const wm=document.getElementById('walletmsg'),pt=document.getElementById('postable');
    if(!s.wallet.ready){wm.textContent='钱包未配置 — '+esc(s.wallet.err)+'。bot 照常盯盘并记录"本该买什么", 配好 .env 重启即切真钱。';pt.style.display='none';}
    else if(!(s.positions||[]).length){wm.textContent='暂无持仓';pt.style.display='none';}
    else{wm.textContent='';pt.style.display='';
      document.getElementById('positions').innerHTML=s.positions.map(p=>
        `<tr><td>${esc(p.title)}</td><td>${esc(p.side)}</td><td>${fmt(p.size,2)}</td>
        <td>${fmt(p.avg_price,3)}</td><td>${fmt(p.cur_price,3)}</td>
        <td class="${p.pnl_pct>=0?'gn':'rd'}">${fmt(p.pnl_pct,1)}%</td></tr>`).join('');}
    const su=s.summary||{};
    document.getElementById('sumstats').innerHTML=
      `<div class="stat">真钱累计盈亏<b class="${su.real_pnl>=0?'gn':'rd'}">$${fmt(su.real_pnl,2)}</b></div>`+
      `<div class="stat">模拟累计盈亏(已扣费)<b class="${su.paper_pnl>=0?'cy':'rd'}">$${fmt(su.paper_pnl,2)}</b></div>`+
      `<div class="stat">命中率<b>${su.hit_rate==null?'—':fmt(su.hit_rate,0)+'%'}</b></div>`+
      `<div class="stat">已结算<b>${su.won||0} 赢 / ${su.lost||0} 输</b></div>`;
    document.getElementById('history').innerHTML=(s.history||[]).map(p=>{
      const pc=p.status==='won'?'gn':(p.status==='lost'?'rd':'muted');
      return `<tr><td class="muted">${esc(p.date)}</td><td>${esc(p.city)}</td><td>${esc(p.bucket_label)}</td>
      <td>${p.best_ask==null?'—':fmt(p.best_ask,3)}</td><td class="${pc}">${esc(p.status_cn)}${p.mode==='real'?'':(p.mode?' <span class=muted>(模拟)</span>':'')}</td>
      <td>${esc(p.winning_label)||'—'}</td><td class="${(p.pnl||0)>=0?'gn':'rd'}">${p.pnl==null?'—':fmt(p.pnl,2)}</td>
      <td class="reason">${esc(p.reason)}</td></tr>`;
    }).join('')||'<tr><td colspan="8" class="muted">还没有历史记录</td></tr>';
    document.getElementById('logs').textContent=(s.log_tail||[]).join('');
  }catch(e){console.log('load fail',e)}
}
async function haltToggle(){
  if(!HALT&&!confirm('确定打开紧急停止? 打开后所有城市都不再下单。'))return;
  await fetch('/api/halt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({on:!HALT})});load();
}
async function clearAlerts(){await fetch('/api/alerts/clear',{method:'POST'});load();}
load();setInterval(load,10000);
</script>
</body>
</html>
"""
