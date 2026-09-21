from flask import Flask, render_template_string, jsonify, request as flask_request
from modules.db import get_recent_events, get_daily_spend, get_conn, get_current_phase
from datetime import datetime, timedelta
import json
import threading
import logging
import subprocess

log = logging.getLogger("dashboard")

_bot_instance = None
_last_scan_time = None
_scan_running = False

def set_bot(bot):
    global _bot_instance
    _bot_instance = bot

def record_scan_time():
    global _last_scan_time
    _last_scan_time = datetime.now()

INDEX_HTML = r"""
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polymarket Bot v2</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg:#060610;--bg2:#0c0c1d;--surface:#111128;--surface2:#16163a;--surface3:#1c1c48;
  --border:#1e1e4a;--border2:#2a2a5c;
  --text:#e8e8ff;--text2:#9898c8;--text3:#5858a0;
  --accent:#00e5a0;--accent2:#00c8ff;--accent-dim:rgba(0,229,160,0.08);
  --red:#ff4070;--red-dim:rgba(255,64,112,0.08);
  --amber:#ffc040;--amber-dim:rgba(255,192,64,0.08);
  --violet:#8060ff;--violet-dim:rgba(128,96,255,0.08);
  --grad:linear-gradient(135deg,#00e5a0 0%,#00c8ff 100%);
  --grad2:linear-gradient(135deg,#8060ff 0%,#c060ff 100%);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;top:-200px;left:-200px;width:600px;height:600px;background:radial-gradient(circle,rgba(0,229,160,0.03),transparent 60%);pointer-events:none;z-index:0}
body::after{content:'';position:fixed;bottom:-200px;right:-200px;width:600px;height:600px;background:radial-gradient(circle,rgba(0,200,255,0.03),transparent 60%);pointer-events:none;z-index:0}

/* NAV */
nav{background:rgba(6,6,16,0.9);backdrop-filter:blur(24px);border-bottom:1px solid var(--border);padding:0 28px;height:56px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.nav-left{display:flex;align-items:center;gap:12px}
.logo{width:28px;height:28px;border-radius:8px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-weight:700;color:#060610;font-size:14px;font-family:'JetBrains Mono',monospace}
.nav-title{font-size:14px;font-weight:600;letter-spacing:-0.3px}
.nav-title span{color:var(--text3);font-weight:400;margin-left:8px;font-size:12px}
.nav-right{display:flex;align-items:center;gap:16px}
.live-pill{display:flex;align-items:center;gap:5px;padding:4px 12px;background:var(--accent-dim);border:1px solid rgba(0,229,160,0.2);border-radius:20px;font-size:10px;font-weight:600;color:var(--accent);text-transform:uppercase;letter-spacing:1px}
.live-dot{width:5px;height:5px;border-radius:50%;background:var(--accent);animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(0,229,160,0.4)}50%{opacity:0.5;box-shadow:0 0 0 4px rgba(0,229,160,0)}}
.nav-clock{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text3)}
.refresh-badge{font-size:10px;color:var(--text3);background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:3px 10px;font-family:'JetBrains Mono',monospace}

.wrap{max-width:1400px;margin:0 auto;padding:20px 20px 60px;position:relative;z-index:1}

/* TOAST */
.toast{position:fixed;top:70px;right:20px;padding:12px 18px;border-radius:10px;font-size:12px;font-weight:500;z-index:200;opacity:0;transform:translateY(-10px);transition:all .3s;max-width:360px}
.toast.show{opacity:1;transform:translateY(0)}
.toast.ok{background:var(--accent-dim);border:1px solid rgba(0,229,160,0.3);color:var(--accent)}
.toast.err{background:var(--red-dim);border:1px solid rgba(255,64,112,0.3);color:var(--red)}
.toast.info{background:rgba(0,200,255,0.1);border:1px solid rgba(0,200,255,0.3);color:var(--accent2)}

/* CONTROL BAR */
.ctrl{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.ctrl-left{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.ctrl-left .phase{padding:4px 12px;border-radius:8px;background:var(--violet-dim);border:1px solid rgba(128,96,255,0.2);color:var(--violet);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px}
.ctrl-left .next-scan{font-size:11px;color:var(--text3);font-family:'JetBrains Mono',monospace}
.ctrl-left .next-scan b{color:var(--accent2)}
.scan-status{font-size:11px;padding:4px 12px;border-radius:8px;font-weight:500}
.scan-status.idle{background:var(--surface2);color:var(--text3);border:1px solid var(--border)}
.scan-status.running{background:var(--accent-dim);color:var(--accent);border:1px solid rgba(0,229,160,0.2);animation:glow 2s ease-in-out infinite}
@keyframes glow{0%,100%{box-shadow:0 0 0 0 rgba(0,229,160,0.1)}50%{box-shadow:0 0 12px 0 rgba(0,229,160,0.15)}}
.ctrl-btns{display:flex;gap:8px;flex-wrap:wrap}
.btn{padding:8px 16px;border-radius:8px;border:1px solid var(--border);background:var(--surface2);color:var(--text2);font-family:'Space Grotesk',sans-serif;font-size:11px;font-weight:600;cursor:pointer;transition:all .15s;display:flex;align-items:center;gap:5px}
.btn:hover{border-color:var(--accent);color:var(--accent);background:var(--accent-dim)}
.btn.primary{background:linear-gradient(135deg,rgba(0,229,160,0.12),rgba(0,200,255,0.12));border-color:rgba(0,229,160,0.25)}
.btn.danger:hover{border-color:var(--red);color:var(--red);background:var(--red-dim)}
.btn:disabled{opacity:0.35;cursor:not-allowed}
.btn .sp{width:12px;height:12px;border:2px solid var(--text3);border-top-color:var(--accent);border-radius:50%;animation:spin 0.6s linear infinite;display:none}
.btn.loading .sp{display:inline-block}
.btn.loading{opacity:0.6;pointer-events:none}
@keyframes spin{to{transform:rotate(360deg)}}

/* METRICS */
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
@media(max-width:1100px){.metrics{grid-template-columns:repeat(3,1fr)}}
@media(max-width:650px){.metrics{grid-template-columns:repeat(2,1fr)}}
.m{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;position:relative;overflow:hidden;transition:all .2s}
.m:hover{border-color:var(--border2);transform:translateY(-1px)}
.m::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.m.g::before{background:var(--grad)}.m.r::before{background:linear-gradient(90deg,var(--red),#ff8060)}.m.b::before{background:linear-gradient(90deg,var(--accent2),var(--violet))}.m.a::before{background:linear-gradient(90deg,var(--amber),#ff8040)}.m.v::before{background:var(--grad2)}
.m-icon{font-size:16px;margin-bottom:8px}
.m-label{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--text3);margin-bottom:6px}
.m-val{font-size:24px;font-weight:700;font-family:'JetBrains Mono',monospace;letter-spacing:-1px;line-height:1}
.m-sub{font-size:10px;color:var(--text3);margin-top:6px}

/* GRID */
.grid{display:grid;grid-template-columns:3fr 2fr;gap:16px;margin-bottom:20px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.grid-full{margin-bottom:20px}

/* CARD */
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.card-h{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.card-h h2{font-size:12px;font-weight:600;color:var(--text2);letter-spacing:0.5px}
.cnt{font-size:9px;padding:3px 8px;border-radius:8px;font-weight:600;font-family:'JetBrains Mono',monospace}
.cnt-g{background:var(--accent-dim);color:var(--accent)}.cnt-b{background:rgba(0,200,255,0.08);color:var(--accent2)}.cnt-v{background:var(--violet-dim);color:var(--violet)}
.card-b{max-height:400px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--border2) transparent}
.card-b::-webkit-scrollbar{width:3px}.card-b::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}

/* POSITIONS */
.pos{display:block;padding:12px 18px;border-bottom:1px solid var(--border);cursor:pointer;transition:all .12s;text-decoration:none;color:inherit}
.pos:hover{background:var(--surface2);padding-left:22px}
.pos:last-child{border-bottom:none}
.pos-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.pos-name{font-size:12px;font-weight:500;max-width:65%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pos-pnl{font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:700}
.pos-bot{display:flex;gap:14px;font-size:10px;color:var(--text3)}

/* CHART */
.chart-wrap{padding:16px;height:240px}

/* LOG ROW */
.log-r{padding:8px 18px;border-bottom:1px solid rgba(30,30,74,0.5);font-size:11px;display:grid;grid-template-columns:60px 54px 1fr;gap:8px;align-items:start;transition:background .1s}
.log-r:hover{background:var(--surface2)}.log-r:last-child{border-bottom:none}
.log-r .lt{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text3)}
.log-r .ld{color:var(--text2);line-height:1.4;font-size:10px;word-break:break-word}
.tag{display:inline-block;padding:1px 6px;border-radius:3px;font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px}
.tag-buy{background:var(--accent-dim);color:var(--accent)}.tag-sell{background:var(--red-dim);color:var(--red)}.tag-scan{background:var(--violet-dim);color:var(--violet)}.tag-error{background:var(--red-dim);color:var(--red)}.tag-hold{background:rgba(0,200,255,0.08);color:var(--accent2)}.tag-add{background:var(--amber-dim);color:var(--amber)}

/* RESEARCH SECTION */
.research-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:20px}
.research-item{padding:14px 18px;border-bottom:1px solid var(--border)}
.research-item:last-child{border-bottom:none}
.ri-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.ri-time{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text3)}
.ri-status{font-size:10px;font-weight:600;padding:2px 8px;border-radius:6px}
.ri-status.found{background:var(--accent-dim);color:var(--accent)}
.ri-status.none{background:var(--surface2);color:var(--text3)}
.ri-status.error{background:var(--red-dim);color:var(--red)}
.ri-detail{font-size:11px;color:var(--text2);line-height:1.5}

/* LIVE LOG */
.log-live{background:var(--bg2);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.log-live .card-h{background:var(--surface);border-bottom:1px solid var(--border)}
.log-content{height:320px;overflow-y:auto;padding:10px 14px;font-family:'JetBrains Mono',monospace;font-size:10px;line-height:1.7;scrollbar-width:thin;scrollbar-color:var(--border2) transparent}
.log-content::-webkit-scrollbar{width:3px}.log-content::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
.log-line{padding:1px 0}
.log-line .ts{color:var(--text3)}
.log-line .INFO{color:var(--accent2)}
.log-line .WARNING{color:var(--amber)}
.log-line .ERROR{color:var(--red)}
.log-line .msg{color:var(--text2)}

.empty{padding:40px;text-align:center;color:var(--text3);font-size:11px}
.section-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:var(--text3);margin-bottom:10px;padding-left:2px}
footer{text-align:center;padding:20px;font-size:10px;color:var(--text3)}
</style>
</head>
<body>
<nav>
  <div class="nav-left">
    <div class="logo">P</div>
    <div class="nav-title">Polymarket Bot <span>v2.0 Claude Research</span></div>
  </div>
  <div class="nav-right">
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
    <div class="refresh-badge" id="refreshBadge">30s</div>
    <div class="nav-clock" id="clock"></div>
  </div>
</nav>

<div id="toast" class="toast"></div>

<div class="wrap">
  <!-- CONTROL BAR -->
  <div class="ctrl">
    <div class="ctrl-left">
      <span class="phase">{{ phase }}</span>
      <span class="scan-status {{ 'running' if scan_running else 'idle' }}">{{ 'Research进行中...' if scan_running else '待命中' }}</span>
      <span class="next-scan">上次扫描: <b>{{ last_scan }}</b> &nbsp;|&nbsp; 下次: <b id="countdown">{{ next_scan }}</b></span>
    </div>
    <div class="ctrl-btns">
      <button class="btn primary" onclick="doAction('scan')"><span class="sp"></span>🔍 立即搜索</button>
      <button class="btn" onclick="doAction('check')"><span class="sp"></span>📊 检查持仓</button>
      <button class="btn" onclick="doAction('refresh')">🔄 刷新</button>
      <button class="btn danger" onclick="if(confirm('确定停止?'))doAction('stop')">⏹ 停止</button>
    </div>
  </div>

  <!-- METRICS -->
  <div class="metrics">
    <div class="m {{ 'g' if total_pnl >= 0 else 'r' }}">
      <div class="m-icon">💰</div><div class="m-label">总盈亏</div>
      <div class="m-val" style="color:{{ '#00e5a0' if total_pnl >= 0 else '#ff4070' }}">${{ "%.2f"|format(total_pnl) }}</div>
      <div class="m-sub">所有持仓合计</div>
    </div>
    <div class="m g">
      <div class="m-icon">📊</div><div class="m-label">今日花费</div>
      <div class="m-val">${{ "%.2f"|format(daily_spend) }}</div>
      <div class="m-sub">剩余 ${{ "%.2f"|format(5.00 - daily_spend) }} / $5.00</div>
    </div>
    <div class="m b">
      <div class="m-icon">📦</div><div class="m-label">活跃持仓</div>
      <div class="m-val">{{ positions|length }}</div>
      <div class="m-sub">个标的</div>
    </div>
    <div class="m a">
      <div class="m-icon">⚡</div><div class="m-label">今日交易</div>
      <div class="m-val">{{ today_trades }}</div>
      <div class="m-sub">次操作</div>
    </div>
    <div class="m v">
      <div class="m-icon">🔬</div><div class="m-label">总扫描次数</div>
      <div class="m-val">{{ scan_count }}</div>
      <div class="m-sub">Claude Research调用</div>
    </div>
  </div>

  <!-- RESEARCH HISTORY -->
  <div class="section-label">🔬 Research历史</div>
  <div class="research-card">
    <div class="card-h"><h2>最近的Claude Research结果</h2><span class="cnt cnt-v">{{ research_events|length }}</span></div>
    <div class="card-b" style="max-height:200px">
      {% for e in research_events %}
      <div class="research-item">
        <div class="ri-top">
          <span class="ri-time">{{ e.timestamp[5:16] }}</span>
          {% if 'buy' in (e.event_type or '') %}
          <span class="ri-status found">✓ 找到标的</span>
          {% elif 'error' in (e.detail or '') %}
          <span class="ri-status error">✗ 错误</span>
          {% else %}
          <span class="ri-status none">— 无推荐</span>
          {% endif %}
        </div>
        <div class="ri-detail">
          {% if e.market_slug %}📍 {{ e.market_slug }}{% endif %}
          {{ (e.detail or '')[:120] }}
        </div>
      </div>
      {% endfor %}
      {% if not research_events %}<div class="empty">暂无Research记录</div>{% endif %}
    </div>
  </div>

  <!-- POSITIONS + CHART -->
  <div class="section-label">📦 持仓与盈亏</div>
  <div class="grid">
    <div class="card">
      <div class="card-h"><h2>持仓总览</h2><span class="cnt cnt-g">{{ positions|length }}</span></div>
      <div class="card-b">
        {% for p in positions %}
        <a class="pos" href="/position/{{ loop.index0 }}">
          <div class="pos-top">
            <span class="pos-name">{{ p.market_slug[:45] }}</span>
            <span class="pos-pnl" style="color:{{ '#00e5a0' if p.pnl_pct >= 0 else '#ff4070' }}">{{ "%+.1f"|format(p.pnl_pct) }}%</span>
          </div>
          <div class="pos-bot">
            <span>{{ p.side }}</span>
            <span>入 ${{ "%.4f"|format(p.avg_price) }}</span>
            <span>现 ${{ "%.4f"|format(p.current_price) }}</span>
            <span>{{ "%.1f"|format(p.size) }}份</span>
          </div>
        </a>
        {% endfor %}
        {% if not positions %}<div class="empty">暂无持仓</div>{% endif %}
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h2>盈亏分布</h2></div>
      <div class="chart-wrap"><canvas id="pnlChart"></canvas></div>
    </div>
  </div>

  <!-- TRADE LOG + SYSTEM LOG -->
  <div class="section-label">📝 操作记录</div>
  <div class="grid">
    <div class="card">
      <div class="card-h"><h2>交易记录</h2><span class="cnt cnt-g">{{ trade_events|length }}</span></div>
      <div class="card-b">
        {% for e in trade_events %}
        <div class="log-r"><div class="lt">{{ e.timestamp[5:16] }}</div><div><span class="tag tag-{{ e.event_type }}">{{ e.event_type }}</span></div><div class="ld"><b>{{ (e.market_slug or '-')[:28] }}</b> {{ (e.detail or '')[:60] }}</div></div>
        {% endfor %}
        {% if not trade_events %}<div class="empty">暂无交易</div>{% endif %}
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h2>系统事件</h2><span class="cnt cnt-b">{{ events|length }}</span></div>
      <div class="card-b">
        {% for e in events %}
        <div class="log-r"><div class="lt">{{ e.timestamp[5:16] }}</div><div><span class="tag tag-{{ e.event_type }}">{{ e.event_type }}</span></div><div class="ld">{{ (e.market_slug or '')[:20] }} {{ (e.detail or '')[:50] }}</div></div>
        {% endfor %}
        {% if not events %}<div class="empty">暂无数据</div>{% endif %}
      </div>
    </div>
  </div>

  <!-- LIVE LOG -->
  <div class="section-label">🖥 实时日志</div>
  <div class="log-live">
    <div class="card-h">
      <h2>Bot Log</h2>
      <div style="display:flex;align-items:center;gap:8px">
        <div class="live-pill" style="font-size:9px"><div class="live-dot"></div>3秒刷新</div>
        <button class="btn" onclick="scrollLogBottom()" style="font-size:10px;padding:4px 10px">↓ 底部</button>
      </div>
    </div>
    <div class="log-content" id="logBox">Loading...</div>
  </div>
</div>

<footer>Polymarket Bot v2.0 — Claude Research Single Engine — {{ now }}</footer>

<script>
// === REFRESH COUNTDOWN ===
let refreshSec = 30;
setInterval(() => {
  refreshSec--;
  document.getElementById('refreshBadge').textContent = refreshSec + 's';
  if (refreshSec <= 0) location.reload();
}, 1000);

// === CLOCK ===
setInterval(() => {
  document.getElementById('clock').textContent = new Date().toLocaleString('zh-CN', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
}, 1000);

// === NEXT SCAN COUNTDOWN ===
const nextScanStr = "{{ next_scan_iso }}";
if (nextScanStr && nextScanStr !== "N/A") {
  const nextScan = new Date(nextScanStr);
  setInterval(() => {
    const now = new Date();
    const diff = Math.max(0, Math.floor((nextScan - now) / 1000));
    const h = Math.floor(diff / 3600);
    const m = Math.floor((diff % 3600) / 60);
    const s = diff % 60;
    document.getElementById('countdown').textContent =
      (h > 0 ? h + 'h ' : '') + m + 'm ' + s + 's';
  }, 1000);
}

// === PNL CHART ===
const pd = {{ pnl_json|safe }};
if (pd.labels.length > 0) {
  new Chart(document.getElementById('pnlChart'), {
    type:'bar',
    data:{labels:pd.labels,datasets:[{data:pd.values,
      backgroundColor:pd.values.map(v=>v>=0?'rgba(0,229,160,0.5)':'rgba(255,64,112,0.5)'),
      borderColor:pd.values.map(v=>v>=0?'#00e5a0':'#ff4070'),borderWidth:1,borderRadius:6}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{color:'#5858a0',font:{size:9,family:'JetBrains Mono'}},grid:{display:false}},
              y:{ticks:{color:'#5858a0',callback:v=>v+'%',font:{size:9,family:'JetBrains Mono'}},grid:{color:'rgba(30,30,74,0.5)'}}}}
  });
}

// === LIVE LOGS ===
function fetchLogs() {
  fetch('/api/logs').then(r=>r.json()).then(d=>{
    if(!d.ok) return;
    const box = document.getElementById('logBox');
    const wasAtBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    box.innerHTML = d.lines.map(line => {
      let cls='';
      if(line.includes('[INFO]'))cls='INFO';
      else if(line.includes('[WARNING]'))cls='WARNING';
      else if(line.includes('[ERROR]'))cls='ERROR';
      const ts = line.substring(0,19);
      const rest = line.substring(20);
      return '<div class="log-line"><span class="ts">'+ts+'</span> <span class="'+cls+'">['+cls+']</span> <span class="msg">'+rest.replace(/\[(?:INFO|WARNING|ERROR)\]\s?/,'')+'</span></div>';
    }).join('');
    if(wasAtBottom) box.scrollTop = box.scrollHeight;
  });
}
fetchLogs();
setInterval(fetchLogs, 3000);
function scrollLogBottom(){document.getElementById('logBox').scrollTop=999999}

// === CONTROL ACTIONS ===
function doAction(action) {
  const btn = event.target.closest('.btn');
  if(btn) btn.classList.add('loading');
  showToast('info', action==='scan'?'Claude Research启动中...':action==='check'?'检查持仓...':action==='stop'?'停止中...':'刷新中...');
  fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})})
    .then(r=>r.json()).then(d=>{
      if(btn)btn.classList.remove('loading');
      showToast(d.ok?'ok':'err', d.message);
      if(action==='refresh')setTimeout(()=>location.reload(),800);
    }).catch(()=>{if(btn)btn.classList.remove('loading');showToast('err','网络错误')});
}
function showToast(t,msg){const e=document.getElementById('toast');e.className='toast '+t+' show';e.textContent=msg;setTimeout(()=>e.classList.remove('show'),3500)}
</script>
</body>
</html>
"""

DETAIL_HTML = r"""
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ p.market_slug[:40] }}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#060610;--surface:#111128;--border:#1e1e4a;--text:#e8e8ff;--text2:#9898c8;--text3:#5858a0;--accent:#00e5a0;--red:#ff4070;--violet:#8060ff}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
nav{background:rgba(6,6,16,0.9);backdrop-filter:blur(24px);border-bottom:1px solid var(--border);padding:0 28px;height:56px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:100}
nav a{color:var(--text2);text-decoration:none;font-size:12px;font-weight:500;transition:color .15s}
nav a:hover{color:var(--accent)}
nav .sep{color:var(--text3)}
nav .cur{color:var(--text);font-weight:700}
.wrap{max-width:800px;margin:0 auto;padding:28px 20px}
h1{font-size:18px;font-weight:700;margin-bottom:8px;line-height:1.4;letter-spacing:-0.3px}
.sub{display:flex;align-items:center;gap:8px;margin-bottom:28px;font-size:11px;color:var(--text2)}
.pill{padding:3px 12px;border-radius:16px;font-size:10px;font-weight:700}
.pill-y{background:rgba(0,229,160,0.1);color:var(--accent);border:1px solid rgba(0,229,160,0.2)}
.pill-n{background:rgba(255,64,112,0.1);color:var(--red);border:1px solid rgba(255,64,112,0.2)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
@media(max-width:600px){.stats{grid-template-columns:repeat(2,1fr)}}
.s{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center}
.s-label{font-size:9px;text-transform:uppercase;letter-spacing:1.5px;color:var(--text3);margin-bottom:6px;font-weight:600}
.s-val{font-size:22px;font-weight:700;font-family:'JetBrains Mono',monospace}
.info{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:20px}
.info h3{font-size:11px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:1px;padding:14px 18px;border-bottom:1px solid var(--border)}
.row{display:flex;justify-content:space-between;padding:10px 18px;border-bottom:1px solid rgba(30,30,74,0.5);font-size:12px}
.row:last-child{border-bottom:none}
.row .k{color:var(--text3)}.row .v{font-family:'JetBrains Mono',monospace;font-weight:500}
.back{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;background:var(--surface);border:1px solid var(--border);border-radius:8px;color:var(--text2);text-decoration:none;font-size:12px;font-weight:500;transition:all .15s}
.back:hover{border-color:var(--accent);color:var(--accent)}
.green{color:var(--accent)}.red{color:var(--red)}
.ch{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px;margin-bottom:20px}
.ch h3{font-size:11px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
.ch-area{height:180px}
</style>
</head>
<body>
<nav><a href="/">← 控制台</a><span class="sep">/</span><span class="cur">持仓详情</span></nav>
<div class="wrap">
  <h1>{{ p.market_slug }}</h1>
  <div class="sub"><span class="pill {{ 'pill-y' if p.side == 'Yes' else 'pill-n' }}">{{ p.side }}</span></div>
  <div class="stats">
    <div class="s"><div class="s-label">盈亏</div><div class="s-val {{ 'green' if p.pnl_pct >= 0 else 'red' }}">{{ "%+.1f"|format(p.pnl_pct) }}%</div></div>
    <div class="s"><div class="s-label">数量</div><div class="s-val">{{ "%.1f"|format(p.size) }}</div></div>
    <div class="s"><div class="s-label">成本</div><div class="s-val">${{ "%.2f"|format(p.avg_price * p.size) }}</div></div>
    <div class="s"><div class="s-label">现值</div><div class="s-val">${{ "%.2f"|format(p.current_price * p.size) }}</div></div>
  </div>
  <div class="ch"><h3>买入 vs 当前</h3><div class="ch-area"><canvas id="pc"></canvas></div></div>
  <div class="info">
    <h3>详细信息</h3>
    <div class="row"><span class="k">方向</span><span class="v">{{ p.side }}</span></div>
    <div class="row"><span class="k">买入价</span><span class="v">${{ "%.4f"|format(p.avg_price) }}</span></div>
    <div class="row"><span class="k">当前价</span><span class="v">${{ "%.4f"|format(p.current_price) }}</span></div>
    <div class="row"><span class="k">数量</span><span class="v">{{ "%.2f"|format(p.size) }}</span></div>
    <div class="row"><span class="k">浮盈</span><span class="v {{ 'green' if p.pnl_pct >= 0 else 'red' }}">${{ "%.4f"|format((p.current_price - p.avg_price) * p.size) }}</span></div>
    <div class="row"><span class="k">盈亏%</span><span class="v {{ 'green' if p.pnl_pct >= 0 else 'red' }}">{{ "%+.1f"|format(p.pnl_pct) }}%</span></div>
  </div>
  <a href="/" class="back">← 返回控制台</a>
</div>
<script>
new Chart(document.getElementById('pc'),{
  type:'bar',data:{labels:['买入价','当前价'],datasets:[{data:[{{ p.avg_price }},{{ p.current_price }}],
    backgroundColor:['rgba(128,96,255,0.4)','{{ "rgba(0,229,160,0.4)" if p.current_price >= p.avg_price else "rgba(255,64,112,0.4)" }}'],
    borderColor:['#8060ff','{{ "#00e5a0" if p.current_price >= p.avg_price else "#ff4070" }}'],borderWidth:2,borderRadius:8}]},
  options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{display:false}},
    scales:{x:{ticks:{color:'#5858a0',callback:v=>'$'+v.toFixed(3)},grid:{color:'rgba(30,30,74,0.4)'}},y:{ticks:{color:'#9898c8'},grid:{display:false}}}}
});
</script>
</body>
</html>
"""


def create_app():
    app = Flask(__name__)

    def _pos():
        try:
            from modules.executor import Executor
            return Executor().get_positions()
        except:
            return []

    def _balance():
        try:
            from modules.executor import Executor
            return Executor().get_balance()
        except:
            return 0

    @app.route("/")
    def index():
        events = get_recent_events(100)
        daily_spend = get_daily_spend()
        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_conn()
        today_trades = conn.execute("SELECT COUNT(*) FROM events WHERE event_type IN ('buy','sell','add') AND timestamp LIKE ?", (today+"%",)).fetchone()[0]
        conn.close()
        positions = _pos()
        balance = _balance()
        trade_events = [e for e in events if e["event_type"] in ("buy","sell","add")]
        research_events = [e for e in events if e["event_type"] in ("scan","buy","error") and e.get("detail")][:10]
        total_pnl = sum((p["current_price"]-p["avg_price"])*p.get("size",0) for p in positions)
        phase = get_current_phase()
        scan_count = len([e for e in events if e["event_type"] in ("scan","buy")])

        # Last scan time
        scan_events = [e for e in events if e["event_type"] in ("scan","buy")]
        last_scan = scan_events[0]["timestamp"][5:16] if scan_events else "N/A"
        
        # Next scan
        next_scan = "N/A"
        next_scan_iso = "N/A"
        if scan_events:
            try:
                last_dt = datetime.fromisoformat(scan_events[0]["timestamp"])
                next_dt = last_dt + timedelta(hours=4)
                next_scan = next_dt.strftime("%H:%M")
                next_scan_iso = next_dt.isoformat()
            except:
                pass

        global _scan_running
        pnl_data = {"labels": [p["market_slug"][:15] for p in positions], "values": [round(p.get("pnl_pct",0),1) for p in positions]}
        
        return render_template_string(INDEX_HTML,
            events=events, trade_events=trade_events, research_events=research_events,
            daily_spend=daily_spend, positions=positions, today_trades=today_trades,
            next_scan=next_scan, next_scan_iso=next_scan_iso, last_scan=last_scan,
            total_pnl=total_pnl, balance=balance, phase=phase, scan_count=scan_count,
            scan_running=_scan_running, pnl_json=json.dumps(pnl_data),
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @app.route("/position/<int:idx>")
    def detail(idx):
        positions = _pos()
        if idx < 0 or idx >= len(positions):
            return "Not found", 404
        p = positions[idx]
        for k in ["size","asset","condition_id","pnl_pct"]:
            p.setdefault(k, 0 if k in ("size","pnl_pct") else "")
        return render_template_string(DETAIL_HTML, p=p)

    @app.route("/api/control", methods=["POST"])
    def control():
        global _scan_running
        data = flask_request.get_json() or {}
        action = data.get("action", "")

        if action == "scan":
            if _scan_running:
                return jsonify({"ok": False, "message": "Research已在进行中，请等待完成"})
            if _bot_instance:
                def run_scan():
                    global _scan_running
                    _scan_running = True
                    try:
                        _bot_instance.discover()
                    finally:
                        _scan_running = False
                        record_scan_time()
                threading.Thread(target=run_scan, daemon=True).start()
                return jsonify({"ok": True, "message": "Claude Research启动中...预计5-20分钟"})
            return jsonify({"ok": False, "message": "Bot实例未运行"})

        elif action == "check":
            if _bot_instance:
                threading.Thread(target=_bot_instance.check_positions, daemon=True).start()
                return jsonify({"ok": True, "message": "持仓检查已启动"})
            return jsonify({"ok": False, "message": "Bot实例未运行"})

        elif action == "refresh":
            return jsonify({"ok": True, "message": "数据已刷新"})

        elif action == "stop":
            import os, signal
            os.kill(os.getpid(), signal.SIGTERM)
            return jsonify({"ok": True, "message": "Bot正在停止..."})

        return jsonify({"ok": False, "message": "未知操作"})

    @app.route("/api/status")
    def api_status():
        return jsonify({"daily_spend": get_daily_spend(), "events": get_recent_events(20), "phase": get_current_phase(), "scan_running": _scan_running})

    @app.route("/api/logs")
    def api_logs():
        try:
            result = subprocess.run(["tail", "-80", "bot.log"], capture_output=True, text=True, timeout=5)
            lines = result.stdout.strip().split("\n") if result.stdout else []
            # Filter out noisy /api/logs lines
            filtered = [l for l in lines if "/api/logs" not in l and "GET / HTTP" not in l]
            return jsonify({"ok": True, "lines": filtered[-40:]})
        except:
            return jsonify({"ok": False, "lines": []})

    return app
