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
:root{--bg:#060610;--bg2:#0c0c1d;--sf:#111128;--sf2:#16163a;--bd:#1e1e4a;--bd2:#2a2a5c;--tx:#e8e8ff;--tx2:#9898c8;--tx3:#5858a0;--ac:#00e5a0;--ac2:#00c8ff;--acd:rgba(0,229,160,0.08);--rd:#ff4070;--rdd:rgba(255,64,112,0.08);--am:#ffc040;--amd:rgba(255,192,64,0.08);--vi:#8060ff;--vid:rgba(128,96,255,0.08)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--tx);min-height:100vh}
nav{background:rgba(6,6,16,0.9);backdrop-filter:blur(24px);border-bottom:1px solid var(--bd);padding:0 28px;height:56px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.nl{display:flex;align-items:center;gap:12px}
.logo{width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#00e5a0,#00c8ff);display:flex;align-items:center;justify-content:center;font-weight:700;color:#060610;font-size:14px;font-family:'JetBrains Mono'}
.nt{font-size:14px;font-weight:600}.nt span{color:var(--tx3);font-weight:400;margin-left:8px;font-size:12px}
.nr{display:flex;align-items:center;gap:16px}
.lp{display:flex;align-items:center;gap:5px;padding:4px 12px;background:var(--acd);border:1px solid rgba(0,229,160,0.2);border-radius:20px;font-size:10px;font-weight:600;color:var(--ac);text-transform:uppercase;letter-spacing:1px}
.ld{width:5px;height:5px;border-radius:50%;background:var(--ac);animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
.rb{font-size:10px;color:var(--tx3);background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:3px 10px;font-family:'JetBrains Mono'}
.nc{font-family:'JetBrains Mono';font-size:11px;color:var(--tx3)}
.wrap{max-width:1400px;margin:0 auto;padding:20px 20px 60px;position:relative;z-index:1}
.toast{position:fixed;top:70px;right:20px;padding:12px 18px;border-radius:10px;font-size:12px;font-weight:500;z-index:200;opacity:0;transform:translateY(-10px);transition:all .3s;max-width:360px}
.toast.show{opacity:1;transform:translateY(0)}.toast.ok{background:var(--acd);border:1px solid rgba(0,229,160,0.3);color:var(--ac)}.toast.err{background:var(--rdd);border:1px solid rgba(255,64,112,0.3);color:var(--rd)}.toast.info{background:rgba(0,200,255,0.1);border:1px solid rgba(0,200,255,0.3);color:var(--ac2)}
.ctrl{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.cl{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.cl .ph{padding:4px 12px;border-radius:8px;background:var(--vid);border:1px solid rgba(128,96,255,0.2);color:var(--vi);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.cl .ns{font-size:11px;color:var(--tx3);font-family:'JetBrains Mono'}.cl .ns b{color:var(--ac2)}
.ss{font-size:11px;padding:4px 12px;border-radius:8px;font-weight:500}
.ss.idle{background:var(--sf2);color:var(--tx3);border:1px solid var(--bd)}
.ss.run{background:var(--acd);color:var(--ac);border:1px solid rgba(0,229,160,0.2);animation:glow 2s ease-in-out infinite}
@keyframes glow{0%,100%{box-shadow:0 0 0 rgba(0,229,160,0.1)}50%{box-shadow:0 0 12px rgba(0,229,160,0.15)}}
.cbs{display:flex;gap:8px;flex-wrap:wrap}
.btn{padding:8px 16px;border-radius:8px;border:1px solid var(--bd);background:var(--sf2);color:var(--tx2);font-family:'Space Grotesk';font-size:11px;font-weight:600;cursor:pointer;transition:all .15s;display:flex;align-items:center;gap:5px}
.btn:hover{border-color:var(--ac);color:var(--ac);background:var(--acd)}
.btn.p{background:linear-gradient(135deg,rgba(0,229,160,0.12),rgba(0,200,255,0.12));border-color:rgba(0,229,160,0.25)}
.btn.d:hover{border-color:var(--rd);color:var(--rd);background:var(--rdd)}
.btn:disabled{opacity:.35;cursor:not-allowed}
.btn .sp{width:12px;height:12px;border:2px solid var(--tx3);border-top-color:var(--ac);border-radius:50%;animation:spin .6s linear infinite;display:none}
.btn.loading .sp{display:inline-block}.btn.loading{opacity:.6;pointer-events:none}
@keyframes spin{to{transform:rotate(360deg)}}
.ms{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
@media(max-width:1100px){.ms{grid-template-columns:repeat(3,1fr)}}@media(max-width:650px){.ms{grid-template-columns:repeat(2,1fr)}}
.m{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:16px 18px;position:relative;overflow:hidden;transition:all .2s}
.m:hover{border-color:var(--bd2);transform:translateY(-1px)}
.m::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.m.g::before{background:linear-gradient(90deg,#00e5a0,#00c8ff)}.m.r::before{background:linear-gradient(90deg,#ff4070,#ff8060)}.m.b::before{background:linear-gradient(90deg,#00c8ff,#8060ff)}.m.a::before{background:linear-gradient(90deg,#ffc040,#ff8040)}.m.v::before{background:linear-gradient(90deg,#8060ff,#c060ff)}
.mi{font-size:16px;margin-bottom:8px}.ml{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--tx3);margin-bottom:6px}
.mv{font-size:24px;font-weight:700;font-family:'JetBrains Mono';letter-spacing:-1px;line-height:1}
.msb{font-size:10px;color:var(--tx3);margin-top:6px}
.sl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:var(--tx3);margin-bottom:10px;padding-left:2px}
.grid{display:grid;grid-template-columns:3fr 2fr;gap:16px;margin-bottom:20px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.card{background:var(--sf);border:1px solid var(--bd);border-radius:12px;overflow:hidden}
.ch{padding:14px 18px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}
.ch h2{font-size:12px;font-weight:600;color:var(--tx2);letter-spacing:.5px}
.cnt{font-size:9px;padding:3px 8px;border-radius:8px;font-weight:600;font-family:'JetBrains Mono'}
.cg{background:var(--acd);color:var(--ac)}.cb{background:rgba(0,200,255,0.08);color:var(--ac2)}.cv{background:var(--vid);color:var(--vi)}
.cb2{max-height:400px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--bd2) transparent}
.cb2::-webkit-scrollbar{width:3px}.cb2::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:2px}
.pos{display:block;padding:12px 18px;border-bottom:1px solid var(--bd);cursor:pointer;transition:all .12s;text-decoration:none;color:inherit}
.pos:hover{background:var(--sf2);padding-left:22px}.pos:last-child{border-bottom:none}
.pt{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.pn{font-size:12px;font-weight:500;max-width:65%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pp{font-family:'JetBrains Mono';font-size:12px;font-weight:700}
.pb{display:flex;gap:14px;font-size:10px;color:var(--tx3)}
.cw{padding:16px;height:240px}
.lr{padding:8px 18px;border-bottom:1px solid rgba(30,30,74,0.5);font-size:11px;display:grid;grid-template-columns:60px 54px 1fr;gap:8px;align-items:start;transition:background .1s}
.lr:hover{background:var(--sf2)}.lr:last-child{border-bottom:none}
.lr .lt{font-family:'JetBrains Mono';font-size:9px;color:var(--tx3)}
.lr .ldd{color:var(--tx2);line-height:1.4;font-size:10px;word-break:break-word}
.tag{display:inline-block;padding:1px 6px;border-radius:3px;font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.3px}
.tag-buy{background:var(--acd);color:var(--ac)}.tag-sell{background:var(--rdd);color:var(--rd)}.tag-scan{background:var(--vid);color:var(--vi)}.tag-error{background:var(--rdd);color:var(--rd)}.tag-hold{background:rgba(0,200,255,0.08);color:var(--ac2)}.tag-add{background:var(--amd);color:var(--am)}
.rc{background:var(--sf);border:1px solid var(--bd);border-radius:12px;overflow:hidden;margin-bottom:20px}
.ri{padding:14px 18px;border-bottom:1px solid var(--bd)}.ri:last-child{border-bottom:none}
.rit{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.rit .tm{font-family:'JetBrains Mono';font-size:10px;color:var(--tx3)}
.ris{font-size:10px;font-weight:600;padding:2px 8px;border-radius:6px}
.ris.f{background:var(--acd);color:var(--ac)}.ris.n{background:var(--sf2);color:var(--tx3)}.ris.e{background:var(--rdd);color:var(--rd)}
.rid{font-size:11px;color:var(--tx2);line-height:1.5}
.ll{background:var(--bg2);border:1px solid var(--bd);border-radius:12px;overflow:hidden}
.ll .ch{background:var(--sf);border-bottom:1px solid var(--bd)}
.lc{height:320px;overflow-y:auto;padding:10px 14px;font-family:'JetBrains Mono';font-size:10px;line-height:1.7;scrollbar-width:thin;scrollbar-color:var(--bd2) transparent}
.lc::-webkit-scrollbar{width:3px}.lc::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:2px}
.ll2{padding:1px 0}
.ll2 .ts{color:var(--tx3)}.ll2 .INFO{color:var(--ac2)}.ll2 .WARNING{color:var(--am)}.ll2 .ERROR{color:var(--rd)}.ll2 .msg{color:var(--tx2)}
.emp{padding:40px;text-align:center;color:var(--tx3);font-size:11px}
footer{text-align:center;padding:20px;font-size:10px;color:var(--tx3)}
</style>
</head>
<body>
<nav>
<div class="nl"><div class="logo">P</div><div class="nt">Polymarket Bot <span>v2.0</span></div></div>
<div class="nr"><div class="lp"><div class="ld"></div>LIVE</div><div class="rb" id="rb">30s</div><div class="nc" id="ck"></div></div>
</nav>
<div id="toast" class="toast"></div>
<div class="wrap">
<div class="ctrl">
<div class="cl">
<span class="ph">{{ phase }}</span>
<span class="ss {{ 'run' if scan_running else 'idle' }}">{{ 'Research进行中...' if scan_running else '待命' }}</span>
<span class="ns">上次: <b>{{ last_scan }}</b> | 下次: <b id="cd">{{ next_scan }}</b></span>
</div>
<div class="cbs">
<button class="btn p" onclick="doAction('scan')"><span class="sp"></span>🔍 立即搜索</button>
<button class="btn" onclick="doAction('check')"><span class="sp"></span>📊 检查持仓</button>
<button class="btn" onclick="doAction('refresh')">🔄 刷新</button>
<button class="btn d" onclick="if(confirm('确定?'))doAction('stop')">⏹ 停止</button>
</div>
</div>
<div class="ms">
<div class="m {{ 'g' if total_pnl >= 0 else 'r' }}"><div class="mi">💰</div><div class="ml">总盈亏</div><div class="mv" style="color:{{ '#00e5a0' if total_pnl >= 0 else '#ff4070' }}">${{ "%.2f"|format(total_pnl) }}</div><div class="msb">所有持仓合计</div></div>
<div class="m g"><div class="mi">📊</div><div class="ml">今日花费</div><div class="mv">${{ "%.2f"|format(daily_spend) }}</div><div class="msb">剩余 ${{ "%.2f"|format(5.00-daily_spend) }} / $5</div></div>
<div class="m b"><div class="mi">📦</div><div class="ml">活跃持仓</div><div class="mv">{{ positions|length }}</div><div class="msb">个标的</div></div>
<div class="m a"><div class="mi">⚡</div><div class="ml">今日交易</div><div class="mv">{{ today_trades }}</div><div class="msb">次操作</div></div>
<div class="m v"><div class="mi">🔬</div><div class="ml">扫描次数</div><div class="mv">{{ scan_count }}</div><div class="msb">Research调用</div></div>
</div>
<div class="sl">🔬 Research历史</div>
<div class="rc">
<div class="ch"><h2>最近Claude Research</h2><span class="cnt cv">{{ research_events|length }}</span></div>
<div class="cb2" style="max-height:200px">
{% for e in research_events %}
<div class="ri"><div class="rit"><span class="tm">{{ e.timestamp[5:16] }}</span>
{% if 'buy' in (e.event_type or '') %}<span class="ris f">✓ 找到</span>
{% elif 'error' in (e.detail or '') %}<span class="ris e">✗ 错误</span>
{% else %}<span class="ris n">— 无推荐</span>{% endif %}
</div><div class="rid">{% if e.market_slug %}📍 {{ e.market_slug }} {% endif %}{{ (e.detail or '')[:120] }}</div></div>
{% endfor %}
{% if not research_events %}<div class="emp">暂无Research记录</div>{% endif %}
</div>
</div>
<div class="sl">📦 持仓与盈亏</div>
<div class="grid">
<div class="card"><div class="ch"><h2>持仓总览</h2><span class="cnt cg">{{ positions|length }}</span></div>
<div class="cb2">
{% for p in positions %}
<a class="pos" href="/position/{{ loop.index0 }}"><div class="pt"><span class="pn">{{ p.market_slug[:45] }}</span><span class="pp" style="color:{{ '#00e5a0' if p.pnl_pct >= 0 else '#ff4070' }}">{{ "%+.1f"|format(p.pnl_pct) }}%</span></div><div class="pb"><span>{{ p.side }}</span><span>入 ${{ "%.4f"|format(p.avg_price) }}</span><span>现 ${{ "%.4f"|format(p.current_price) }}</span><span>{{ "%.1f"|format(p.size) }}份</span></div></a>
{% endfor %}
{% if not positions %}<div class="emp">暂无持仓</div>{% endif %}
</div></div>
<div class="card"><div class="ch"><h2>盈亏分布</h2></div><div class="cw"><canvas id="pc"></canvas></div></div>
</div>
<div class="sl">📝 操作记录</div>
<div class="grid">
<div class="card"><div class="ch"><h2>交易记录</h2><span class="cnt cg">{{ trade_events|length }}</span></div>
<div class="cb2">{% for e in trade_events %}<div class="lr"><div class="lt">{{ e.timestamp[5:16] }}</div><div><span class="tag tag-{{ e.event_type }}">{{ e.event_type }}</span></div><div class="ldd"><b>{{ (e.market_slug or '-')[:28] }}</b> {{ (e.detail or '')[:60] }}</div></div>{% endfor %}{% if not trade_events %}<div class="emp">暂无交易</div>{% endif %}</div></div>
<div class="card"><div class="ch"><h2>系统事件</h2><span class="cnt cb">{{ events|length }}</span></div>
<div class="cb2">{% for e in events %}<div class="lr"><div class="lt">{{ e.timestamp[5:16] }}</div><div><span class="tag tag-{{ e.event_type }}">{{ e.event_type }}</span></div><div class="ldd">{{ (e.market_slug or '')[:20] }} {{ (e.detail or '')[:50] }}</div></div>{% endfor %}{% if not events %}<div class="emp">暂无</div>{% endif %}</div></div>
</div>
<div class="sl">🖥 实时日志</div>
<div class="ll">
<div class="ch"><h2>Bot Log</h2><div style="display:flex;align-items:center;gap:8px"><div class="lp" style="font-size:9px"><div class="ld"></div>3s</div><button class="btn" onclick="document.getElementById('lb').scrollTop=999999" style="font-size:10px;padding:4px 10px">↓ 底部</button></div></div>
<div class="lc" id="lb">Loading...</div>
</div>
</div>
<footer>Polymarket Bot v2.0 — Claude Research Engine</footer>
<script>
let rs=30;setInterval(()=>{rs--;document.getElementById('rb').textContent=rs+'s';if(rs<=0)location.reload()},1000);
setInterval(()=>{document.getElementById('ck').textContent=new Date().toLocaleString('zh-CN',{hour:'2-digit',minute:'2-digit',second:'2-digit'})},1000);
const nsi="{{next_scan_iso}}";if(nsi&&nsi!=="N/A"){const nd=new Date(nsi);setInterval(()=>{const d=Math.max(0,Math.floor((nd-new Date())/1000));const h=Math.floor(d/3600),m=Math.floor(d%3600/60),s=d%60;document.getElementById('cd').textContent=(h>0?h+'h ':'')+m+'m '+s+'s'},1000)}
const pd={{pnl_json|safe}};if(pd.labels.length>0){new Chart(document.getElementById('pc'),{type:'bar',data:{labels:pd.labels,datasets:[{data:pd.values,backgroundColor:pd.values.map(v=>v>=0?'rgba(0,229,160,0.5)':'rgba(255,64,112,0.5)'),borderColor:pd.values.map(v=>v>=0?'#00e5a0':'#ff4070'),borderWidth:1,borderRadius:6}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#5858a0',font:{size:9,family:'JetBrains Mono'}},grid:{display:false}},y:{ticks:{color:'#5858a0',callback:v=>v+'%',font:{size:9,family:'JetBrains Mono'}},grid:{color:'rgba(30,30,74,0.5)'}}}}})}
function fl(){fetch('/api/logs').then(r=>r.json()).then(d=>{if(!d.ok)return;const b=document.getElementById('lb');const ab=b.scrollHeight-b.scrollTop-b.clientHeight<40;b.innerHTML=d.lines.map(l=>{let c='';if(l.includes('[INFO]'))c='INFO';else if(l.includes('[WARNING]'))c='WARNING';else if(l.includes('[ERROR]'))c='ERROR';return'<div class="ll2"><span class="ts">'+l.substring(0,19)+'</span> <span class="'+c+'">['+c+']</span> <span class="msg">'+l.substring(20).replace(/\[(?:INFO|WARNING|ERROR)\]\s?/,'')+'</span></div>'}).join('');if(ab)b.scrollTop=b.scrollHeight})}
fl();setInterval(fl,3000);
function doAction(a){const b=event.target.closest('.btn');if(b)b.classList.add('loading');showT('info',a==='scan'?'Research启动中...':a==='check'?'检查持仓...':a==='stop'?'停止中...':'刷新...');fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a})}).then(r=>r.json()).then(d=>{if(b)b.classList.remove('loading');showT(d.ok?'ok':'err',d.message);if(a==='refresh')setTimeout(()=>location.reload(),800)}).catch(()=>{if(b)b.classList.remove('loading');showT('err','网络错误')})}
function showT(t,m){const e=document.getElementById('toast');e.className='toast '+t+' show';e.textContent=m;setTimeout(()=>e.classList.remove('show'),3500)}
</script>
</body>
</html>
"""

DETAIL_HTML = r"""
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ p.market_slug[:40] }}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#060610;--sf:#111128;--bd:#1e1e4a;--tx:#e8e8ff;--tx2:#9898c8;--tx3:#5858a0;--ac:#00e5a0;--rd:#ff4070;--vi:#8060ff}
*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--tx);min-height:100vh}
nav{background:rgba(6,6,16,0.9);backdrop-filter:blur(24px);border-bottom:1px solid var(--bd);padding:0 28px;height:56px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:100}
nav a{color:var(--tx2);text-decoration:none;font-size:12px}nav a:hover{color:var(--ac)}nav .sep{color:var(--tx3)}nav .cur{color:var(--tx);font-weight:700}
.wrap{max-width:800px;margin:0 auto;padding:28px 20px}
h1{font-size:18px;font-weight:700;margin-bottom:8px}
.sub{display:flex;align-items:center;gap:8px;margin-bottom:28px;font-size:11px;color:var(--tx2)}
.pill{padding:3px 12px;border-radius:16px;font-size:10px;font-weight:700}
.py{background:rgba(0,229,160,0.1);color:var(--ac);border:1px solid rgba(0,229,160,0.2)}.pn{background:rgba(255,64,112,0.1);color:var(--rd);border:1px solid rgba(255,64,112,0.2)}
.sts{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}@media(max-width:600px){.sts{grid-template-columns:repeat(2,1fr)}}
.s{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:16px;text-align:center}
.s-l{font-size:9px;text-transform:uppercase;letter-spacing:1.5px;color:var(--tx3);margin-bottom:6px;font-weight:600}
.s-v{font-size:22px;font-weight:700;font-family:'JetBrains Mono'}
.inf{background:var(--sf);border:1px solid var(--bd);border-radius:12px;overflow:hidden;margin-bottom:20px}
.inf h3{font-size:11px;font-weight:600;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;padding:14px 18px;border-bottom:1px solid var(--bd)}
.rw{display:flex;justify-content:space-between;padding:10px 18px;border-bottom:1px solid rgba(30,30,74,0.5);font-size:12px}.rw:last-child{border-bottom:none}
.rw .k{color:var(--tx3)}.rw .v{font-family:'JetBrains Mono';font-weight:500}
.bk{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;background:var(--sf);border:1px solid var(--bd);border-radius:8px;color:var(--tx2);text-decoration:none;font-size:12px;transition:all .15s}.bk:hover{border-color:var(--ac);color:var(--ac)}
.grn{color:var(--ac)}.red{color:var(--rd)}
.chc{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:18px;margin-bottom:20px}
.chc h3{font-size:11px;font-weight:600;color:var(--tx2);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}.cha{height:180px}
</style>
</head>
<body>
<nav><a href="/">← 控制台</a><span class="sep">/</span><span class="cur">持仓详情</span></nav>
<div class="wrap">
<h1>{{ p.market_slug }}</h1>
<div class="sub"><span class="pill {{ 'py' if p.side == 'Yes' else 'pn' }}">{{ p.side }}</span></div>
<div class="sts">
<div class="s"><div class="s-l">盈亏</div><div class="s-v {{ 'grn' if p.pnl_pct >= 0 else 'red' }}">{{ "%+.1f"|format(p.pnl_pct) }}%</div></div>
<div class="s"><div class="s-l">数量</div><div class="s-v">{{ "%.1f"|format(p.size) }}</div></div>
<div class="s"><div class="s-l">成本</div><div class="s-v">${{ "%.2f"|format(p.avg_price * p.size) }}</div></div>
<div class="s"><div class="s-l">现值</div><div class="s-v">${{ "%.2f"|format(p.current_price * p.size) }}</div></div>
</div>
<div class="chc"><h3>买入 vs 当前</h3><div class="cha"><canvas id="pc"></canvas></div></div>
<div class="inf"><h3>详细信息</h3>
<div class="rw"><span class="k">方向</span><span class="v">{{ p.side }}</span></div>
<div class="rw"><span class="k">买入价</span><span class="v">${{ "%.4f"|format(p.avg_price) }}</span></div>
<div class="rw"><span class="k">当前价</span><span class="v">${{ "%.4f"|format(p.current_price) }}</span></div>
<div class="rw"><span class="k">数量</span><span class="v">{{ "%.2f"|format(p.size) }}</span></div>
<div class="rw"><span class="k">浮盈</span><span class="v {{ 'grn' if p.pnl_pct >= 0 else 'red' }}">${{ "%.4f"|format((p.current_price - p.avg_price) * p.size) }}</span></div>
<div class="rw"><span class="k">盈亏%</span><span class="v {{ 'grn' if p.pnl_pct >= 0 else 'red' }}">{{ "%+.1f"|format(p.pnl_pct) }}%</span></div>
</div>
<a href="/" class="bk">← 返回</a>
</div>
<script>
new Chart(document.getElementById('pc'),{type:'bar',data:{labels:['买入价','当前价'],datasets:[{data:[{{p.avg_price}},{{p.current_price}}],backgroundColor:['rgba(128,96,255,0.4)','{{"rgba(0,229,160,0.4)" if p.current_price>=p.avg_price else "rgba(255,64,112,0.4)"}}'],borderColor:['#8060ff','{{"#00e5a0" if p.current_price>=p.avg_price else "#ff4070"}}'],borderWidth:2,borderRadius:8}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#5858a0',callback:v=>'$'+v.toFixed(3)},grid:{color:'rgba(30,30,74,0.4)'}},y:{ticks:{color:'#9898c8'},grid:{display:false}}}}});
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
        scan_events = [e for e in events if e["event_type"] in ("scan","buy")]
        last_scan = scan_events[0]["timestamp"][5:16] if scan_events else "N/A"
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
        pnl_data = {"labels":[p["market_slug"][:15] for p in positions],"values":[round(p.get("pnl_pct",0),1) for p in positions]}
        return render_template_string(INDEX_HTML,events=events,trade_events=trade_events,research_events=research_events,daily_spend=daily_spend,positions=positions,today_trades=today_trades,next_scan=next_scan,next_scan_iso=next_scan_iso,last_scan=last_scan,total_pnl=total_pnl,balance=balance,phase=phase,scan_count=scan_count,scan_running=_scan_running,pnl_json=json.dumps(pnl_data),now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @app.route("/position/<int:idx>")
    def detail(idx):
        positions = _pos()
        if idx<0 or idx>=len(positions): return "Not found",404
        p = positions[idx]
        for k in ["size","asset","condition_id","pnl_pct"]: p.setdefault(k,0 if k in("size","pnl_pct") else "")
        return render_template_string(DETAIL_HTML,p=p)

    @app.route("/api/control", methods=["POST"])
    def control():
        global _scan_running
        data = flask_request.get_json() or {}
        action = data.get("action","")
        if action == "scan":
            if _scan_running:
                return jsonify({"ok":False,"message":"Research已在进行中"})
            if _bot_instance:
                def run_scan():
                    global _scan_running
                    _scan_running = True
                    try: _bot_instance.discover()
                    finally: _scan_running = False; record_scan_time()
                threading.Thread(target=run_scan,daemon=True).start()
                return jsonify({"ok":True,"message":"Claude Research启动...预计5-20分钟"})
            return jsonify({"ok":False,"message":"Bot未运行"})
        elif action == "check":
            if _bot_instance:
                threading.Thread(target=_bot_instance.check_positions,daemon=True).start()
                return jsonify({"ok":True,"message":"持仓检查已启动"})
            return jsonify({"ok":False,"message":"Bot未运行"})
        elif action == "refresh":
            return jsonify({"ok":True,"message":"已刷新"})
        elif action == "stop":
            import os,signal
            os.kill(os.getpid(),signal.SIGTERM)
            return jsonify({"ok":True,"message":"停止中..."})
        return jsonify({"ok":False,"message":"未知"})

    @app.route("/api/status")
    def api_status():
        return jsonify({"daily_spend":get_daily_spend(),"events":get_recent_events(20),"phase":get_current_phase(),"scan_running":_scan_running})

    @app.route("/api/logs")
    def api_logs():
        try:
            result = subprocess.run(["tail","-80","bot.log"],capture_output=True,text=True,timeout=5)
            lines = result.stdout.strip().split("\n") if result.stdout else []
            filtered = [l for l in lines if "/api/logs" not in l and "GET / HTTP" not in l and "GET /api" not in l]
            return jsonify({"ok":True,"lines":filtered[-40:]})
        except:
            return jsonify({"ok":False,"lines":[]})

    return app