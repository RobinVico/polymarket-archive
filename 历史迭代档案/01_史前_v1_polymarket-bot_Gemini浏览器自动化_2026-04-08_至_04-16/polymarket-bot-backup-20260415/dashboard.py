import os
import json
import requests
from flask import Flask, jsonify, Response
from dotenv import load_dotenv

load_dotenv()

DATA_API = "https://data-api.polymarket.com"
FUNDER = os.getenv("POLY_FUNDER")

app = Flask(__name__)

def get_positions():
    positions = requests.get(
        f"{DATA_API}/positions",
        params={"user": FUNDER, "limit": 100},
        timeout=20,
    ).json()
    return [p for p in positions if float(p.get("size", 0)) > 0]

@app.route("/api/positions")
def api_positions():
    try:
        positions = get_positions()
        return jsonify(positions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")

HTML = r'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polymarket Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  min-height:100vh;
  background: linear-gradient(160deg, #0a0b10 0%, #0f1019 40%, #111320 100%);
  font-family: 'Inter', -apple-system, sans-serif;
  color: #e2e8f0;
  padding: 24px 16px;
}
.container { max-width:900px; margin:0 auto; }
.header { margin-bottom:24px; }
.header h1 { font-size:22px; font-weight:800; letter-spacing:-0.03em; display:flex; align-items:center; gap:10px; }
.live-badge { font-size:10px; font-weight:700; color:#22c55e; background:rgba(34,197,94,0.12); padding:3px 8px; border-radius:6px; letter-spacing:0.05em; }
.subtitle { font-size:12px; color:#475569; margin-top:6px; }
.summary { display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; margin-bottom:22px; }
.summary-card { background:linear-gradient(135deg,rgba(30,32,45,0.9),rgba(20,22,32,0.95)); border:1px solid rgba(255,255,255,0.06); border-radius:14px; padding:16px; text-align:center; }
.summary-label { font-size:11px; color:#64748b; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; margin-bottom:6px; }
.summary-val { font-size:24px; font-weight:800; font-family:'JetBrains Mono',monospace; letter-spacing:-0.02em; }
.alert { background:rgba(234,179,8,0.06); border:1px solid rgba(234,179,8,0.2); border-radius:12px; padding:14px 18px; margin-bottom:22px; display:flex; gap:10px; }
.alert-title { font-size:13px; font-weight:700; color:#fde047; margin-bottom:4px; }
.alert-text { font-size:12px; color:#a3a3a3; line-height:1.6; }
.card { background:linear-gradient(135deg,rgba(30,32,45,0.95),rgba(22,24,35,0.98)); border:1px solid rgba(255,255,255,0.06); border-radius:16px; padding:18px 20px; margin-bottom:12px; animation:fadeIn 0.4s ease; }
@keyframes fadeIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
.card-head { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px; }
.card-title { font-size:14px; font-weight:600; line-height:1.4; flex:1; margin-right:12px; }
.outcome { font-size:11px; font-weight:700; color:#000; padding:2px 8px; border-radius:4px; display:inline-block; margin-top:6px; margin-right:8px; }
.outcome.yes { background:#22c55e; }
.outcome.no { background:#ef4444; }
.liq { font-size:11px; font-weight:600; }
.pnl { font-weight:700; font-family:'JetBrains Mono',monospace; font-size:15px; white-space:nowrap; }
.pnl.pos { color:#22c55e; }
.pnl.neg { color:#ef4444; }
.stats { display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:8px; margin-bottom:12px; }
.stat { background:rgba(255,255,255,0.03); border-radius:10px; padding:10px 8px; text-align:center; }
.stat-label { font-size:10px; color:#64748b; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; margin-bottom:4px; }
.stat-val { font-size:14px; font-weight:700; font-family:'JetBrains Mono',monospace; color:#f1f5f9; }
.cost-row { display:flex; justify-content:space-between; padding:8px 12px; background:rgba(255,255,255,0.02); border-radius:8px; margin-bottom:10px; font-size:12px; color:#64748b; }
.cost-row span span { font-family:'JetBrains Mono',monospace; font-weight:600; }
.advice { border-radius:10px; padding:8px 14px; display:flex; align-items:center; gap:8px; font-size:12px; font-weight:600; }
.advice.dead { background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.25); color:#fca5a5; }
.advice.hold { background:rgba(234,179,8,0.08); border:1px solid rgba(234,179,8,0.25); color:#fde047; }
.advice.watch { background:rgba(96,165,250,0.08); border:1px solid rgba(96,165,250,0.25); color:#93c5fd; }
.refresh-bar { text-align:center; font-size:11px; color:#334155; margin-bottom:18px; }
.footer { margin-top:24px; padding:16px 0; border-top:1px solid rgba(255,255,255,0.04); text-align:center; font-size:11px; color:#334155; }
.loading { text-align:center; padding:60px; color:#475569; font-size:14px; }
@media(max-width:600px) {
  .summary { grid-template-columns:1fr; }
  .stats { grid-template-columns:1fr 1fr; }
  .cost-row { flex-direction:column; gap:4px; }
  .summary-val { font-size:20px; }
}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Polymarket Portfolio <span class="live-badge">LIVE</span></h1>
    <div class="subtitle" id="subtitle">加载中...</div>
  </div>
  <div class="refresh-bar" id="refresh-bar"></div>
  <div class="summary" id="summary"></div>
  <div class="alert">
    <span style="font-size:16px">⚠️</span>
    <div>
      <div class="alert-title">注意事项</div>
      <div class="alert-text">
        1. IP 在美国（Geoblock: blocked），读取正常，下单可能被拦<br>
        2. 多数仓位 Bid ≤ 0.001，几乎没有买家<br>
        3. 数据每 30 秒自动刷新
      </div>
    </div>
  </div>
  <div id="cards"><div class="loading">加载仓位数据...</div></div>
  <div class="footer">Polymarket Bot Monitor · Mac mini 24/7</div>
</div>

<script>
function getAdvice(p) {
  const pnl = p.percentPnl;
  const bid = p.bestBid;
  const cur = p.curPrice;
  if (bid === 0 && cur === 0) return { text:"已失效，无法卖出，等待结算", type:"dead", icon:"⚫" };
  if (bid <= 0.001 && pnl < -50) return { text:"流动性极差，建议持有等结算", type:"hold", icon:"🟡" };
  if (bid <= 0.001) return { text:"无买盘，暂时无法退出", type:"hold", icon:"🟡" };
  if (pnl > -5) return { text:"亏损较小，可观望或止损", type:"watch", icon:"🔵" };
  if (pnl <= -30) return { text:"深度亏损，建议持有博结算翻盘", type:"hold", icon:"🟡" };
  return { text:"关注盘口变化，有买盘时可考虑退出", type:"watch", icon:"🔵" };
}

function getLiq(bid) {
  if (bid === 0) return { label:"无", color:"#ef4444" };
  if (bid <= 0.001) return { label:"极低", color:"#ef4444" };
  if (bid <= 0.01) return { label:"低", color:"#f97316" };
  if (bid <= 0.05) return { label:"中", color:"#eab308" };
  return { label:"良好", color:"#22c55e" };
}

function render(positions) {
  const data = positions.map(p => ({
    title: p.title || "",
    outcome: p.outcome || "",
    size: parseFloat(p.size || 0),
    avgPrice: parseFloat(p.avgPrice || 0),
    curPrice: parseFloat(p.curPrice || 0),
    percentPnl: parseFloat(p.percentPnl || 0),
    asset: p.asset || "",
    bestBid: 0,
  }));

  data.forEach(d => {
    d.cost = d.size * d.avgPrice;
    d.curValue = d.size * d.curPrice;
  });

  data.sort((a,b) => b.cost - a.cost);

  const totalCost = data.reduce((s,p) => s + p.cost, 0);
  const totalValue = data.reduce((s,p) => s + p.curValue, 0);
  const totalPnl = totalCost > 0 ? ((totalValue - totalCost) / totalCost * 100) : 0;

  document.getElementById("subtitle").textContent =
    "实时仓位监控 · " + data.length + " 个活跃仓位 · 数据来自 Polymarket API";

  document.getElementById("summary").innerHTML = [
    { label:"总投入", val:"$"+totalCost.toFixed(2), color:"#e2e8f0" },
    { label:"当前总值", val:"$"+totalValue.toFixed(2), color:totalValue>=totalCost?"#22c55e":"#f87171" },
    { label:"总盈亏", val:totalPnl.toFixed(1)+"%", color:totalPnl>=0?"#22c55e":"#ef4444" },
  ].map(c => `
    <div class="summary-card">
      <div class="summary-label">${c.label}</div>
      <div class="summary-val" style="color:${c.color}">${c.val}</div>
    </div>
  `).join("");

  document.getElementById("cards").innerHTML = data.map(p => {
    const liq = getLiq(p.bestBid);
    const advice = getAdvice(p);
    const loss = p.cost - p.curValue;
    return `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">${p.title}</div>
          <span class="outcome ${p.outcome.toLowerCase()}">${p.outcome}</span>
          <span class="liq" style="color:${liq.color}">流动性: ${liq.label}</span>
        </div>
        <div class="pnl ${p.percentPnl>=0?'pos':'neg'}">${p.percentPnl>=0?'+':''}${p.percentPnl.toFixed(2)}%</div>
      </div>
      <div class="stats">
        <div class="stat"><div class="stat-label">持仓数量</div><div class="stat-val">${p.size.toFixed(2)}</div></div>
        <div class="stat"><div class="stat-label">买入均价</div><div class="stat-val">$${p.avgPrice.toFixed(4)}</div></div>
        <div class="stat"><div class="stat-label">当前价格</div><div class="stat-val">${p.curPrice===0?'—':'$'+p.curPrice.toFixed(4)}</div></div>
        <div class="stat"><div class="stat-label">盈亏比</div><div class="stat-val">${p.percentPnl.toFixed(1)}%</div></div>
      </div>
      <div class="cost-row">
        <span>投入 <span style="color:#94a3b8">$${p.cost.toFixed(3)}</span></span>
        <span>当前 <span style="color:${p.curValue>=p.cost?'#22c55e':'#f87171'}">$${p.curValue.toFixed(3)}</span></span>
        <span>浮亏 <span style="color:#f87171">-$${loss.toFixed(3)}</span></span>
      </div>
      <div class="advice ${advice.type}">${advice.icon} ${advice.text}</div>
    </div>`;
  }).join("");
}

let countdown = 30;

async function fetchData() {
  try {
    const res = await fetch("/api/positions");
    const data = await res.json();
    render(data);
    countdown = 30;
  } catch(e) {
    document.getElementById("cards").innerHTML = '<div class="loading">加载失败，30秒后重试...</div>';
  }
}

setInterval(() => {
  countdown--;
  document.getElementById("refresh-bar").textContent = countdown + "秒后刷新";
  if (countdown <= 0) fetchData();
}, 1000);

fetchData();
</script>
</body>
</html>
'''

if __name__ == "__main__":
    print("\n========================================")
    print("  Dashboard 启动!")
    print("  本机访问: http://localhost:5050")
    print("  同WiFi访问: http://你的IP:5050")
    print("========================================\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
