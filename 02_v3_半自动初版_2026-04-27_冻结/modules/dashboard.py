from flask import Flask, render_template_string, jsonify, request as flask_request
from modules.db import get_recent_events, init_db
from modules.executor import Executor
from modules.monitor import TAKE_PROFIT_RULES, TIME_STOP_DAYS, TIME_STOP_MOVE_PP
from modules.prompts import DISCOVERY_PROMPT
from modules.scanner import scan_and_report
from datetime import datetime
import json, subprocess, threading, logging

log = logging.getLogger("dashboard")
_monitor = None

def set_monitor(m):
    global _monitor
    _monitor = m

HTML = r"""
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Polymarket Semi-Auto</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#060610;--sf:#111128;--sf2:#16163a;--bd:#1e1e4a;--tx:#e8e8ff;--tx2:#9898c8;--tx3:#5858a0;--ac:#00e5a0;--ac2:#00c8ff;--rd:#ff4070;--am:#ffc040;--vi:#8060ff;--acd:rgba(0,229,160,0.08);--rdd:rgba(255,64,112,0.08)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--tx);min-height:100vh}
nav{background:rgba(6,6,16,0.9);backdrop-filter:blur(24px);border-bottom:1px solid var(--bd);padding:0 28px;height:56px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.nl{display:flex;align-items:center;gap:12px}
.logo{width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#00e5a0,#00c8ff);display:flex;align-items:center;justify-content:center;font-weight:700;color:#060610;font-size:14px;font-family:'JetBrains Mono'}
.nt{font-size:14px;font-weight:600}.nt span{color:var(--tx3);font-weight:400;margin-left:8px;font-size:12px}
.nr{display:flex;align-items:center;gap:12px}
.lp{display:flex;align-items:center;gap:5px;padding:4px 12px;background:var(--acd);border:1px solid rgba(0,229,160,0.2);border-radius:20px;font-size:10px;font-weight:600;color:var(--ac)}
.ld{width:5px;height:5px;border-radius:50%;background:var(--ac);animation:p 2s ease-in-out infinite}
@keyframes p{0%,100%{opacity:1}50%{opacity:.3}}
.chip{font-family:'JetBrains Mono';font-size:10px;padding:4px 9px;background:var(--sf);color:var(--tx2);border:1px solid var(--bd);border-radius:14px;cursor:pointer;transition:all 0.15s;letter-spacing:0.3px}
.chip:hover{background:var(--sf2);color:var(--tx);border-color:var(--ac)}
.chip:active{transform:scale(0.94)}
.chip-flash{background:var(--acd);color:var(--ac);border-color:var(--ac)}
.tab{font-family:'Space Grotesk';font-size:12px;font-weight:500;padding:8px 16px;background:transparent;color:var(--tx3);border:none;border-bottom:2px solid transparent;cursor:pointer;transition:all 0.15s}
.tab:hover{color:var(--tx2)}
.tab-active{color:var(--ac);border-bottom-color:var(--ac);font-weight:600}
.tag-chip{font-family:'JetBrains Mono';font-size:10px;padding:5px 10px;background:var(--sf);color:var(--tx);border:1px solid var(--bd);border-radius:14px;cursor:pointer;transition:all 0.15s;letter-spacing:0.3px}
.tag-chip:hover{transform:translateY(-1px)}
.tag-chip:active{transform:scale(0.94)}
.tag-chip.tier1{border-color:rgba(0,229,160,0.3)}
.tag-chip.tier1:hover{background:var(--acd);border-color:var(--ac);color:var(--ac)}
.tag-chip.tier2{border-color:rgba(0,200,255,0.3)}
.tag-chip.tier2:hover{background:rgba(0,200,255,0.1);border-color:var(--ac2);color:var(--ac2)}
.tag-chip.tier3{border-color:rgba(128,96,255,0.3)}
.tag-chip.tier3:hover{background:rgba(128,96,255,0.1);border-color:var(--vi);color:var(--vi)}
.tag-chip.flash-tier1{background:var(--acd);border-color:var(--ac);color:var(--ac)}
.tag-chip.flash-tier2{background:rgba(0,200,255,0.15);border-color:var(--ac2);color:var(--ac2)}
.tag-chip.flash-tier3{background:rgba(128,96,255,0.15);border-color:var(--vi);color:var(--vi)}
.btn-primary{background:linear-gradient(135deg,#00e5a0,#00c8ff)!important;color:#060610!important;border:none!important;font-weight:600}
.btn-primary:hover{filter:brightness(1.1);transform:translateY(-1px)}
.rb{font-size:10px;color:var(--tx3);background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:3px 10px;font-family:'JetBrains Mono'}
.wrap{max-width:1400px;margin:0 auto;padding:20px 20px 60px}
.toast{position:fixed;top:70px;right:20px;padding:12px 18px;border-radius:10px;font-size:12px;z-index:200;opacity:0;transform:translateY(-10px);transition:all .3s;max-width:360px}
.toast.show{opacity:1;transform:translateY(0)}.toast.ok{background:var(--acd);border:1px solid rgba(0,229,160,0.3);color:var(--ac)}.toast.err{background:var(--rdd);border:1px solid rgba(255,64,112,0.3);color:var(--rd)}
.sl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:var(--tx3);margin:20px 0 10px 2px}
.ms{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
@media(max-width:900px){.ms{grid-template-columns:repeat(2,1fr)}}
.m{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:16px 18px;position:relative;overflow:hidden}
.m::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.m.g::before{background:linear-gradient(90deg,#00e5a0,#00c8ff)}.m.r::before{background:linear-gradient(90deg,#ff4070,#ff8060)}.m.b::before{background:linear-gradient(90deg,#00c8ff,#8060ff)}.m.v::before{background:linear-gradient(90deg,#8060ff,#c060ff)}
.mi{font-size:16px;margin-bottom:8px}.ml{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--tx3);margin-bottom:6px}
.mv{font-size:24px;font-weight:700;font-family:'JetBrains Mono';letter-spacing:-1px}
.msb{font-size:10px;color:var(--tx3);margin-top:6px}
.card{background:var(--sf);border:1px solid var(--bd);border-radius:12px;overflow:hidden;margin-bottom:16px}
.chd{padding:14px 18px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}
.chd h2{font-size:12px;font-weight:600;color:var(--tx2)}.cnt{font-size:9px;padding:3px 8px;border-radius:8px;font-weight:600;font-family:'JetBrains Mono';background:var(--acd);color:var(--ac)}
.cb{max-height:500px;overflow-y:auto;scrollbar-width:thin}.cb::-webkit-scrollbar{width:3px}.cb::-webkit-scrollbar-thumb{background:var(--bd)}
.pos-hdr,.pos-row{padding:10px 18px;border-bottom:1px solid var(--bd);display:grid;grid-template-columns:minmax(0,2fr) 40px 55px 55px 55px 55px 45px 55px 80px 50px;gap:5px;align-items:center;font-size:11px}
.pos-hdr{font-weight:700;color:var(--tx3);font-size:10px;background:var(--sf2)}
.pos-row:hover{background:var(--sf2)}
.pos-row .nm{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pos-row .mono{font-family:'JetBrains Mono';font-size:10px}
.tp-input{background:var(--bg);border:1px solid var(--bd);color:var(--ac);padding:3px 6px;border-radius:5px;font-family:'JetBrains Mono';font-size:10px;width:48px}
.tp-input:focus{outline:none;border-color:var(--ac)}
.btn-small{background:var(--acd);border:1px solid rgba(0,229,160,0.3);color:var(--ac);padding:3px 8px;border-radius:5px;font-size:9px;cursor:pointer;font-family:'Space Grotesk';font-weight:600;white-space:nowrap}
.btn-small:hover{background:rgba(0,229,160,0.2)}
.triggers{padding:8px 18px 12px 18px;border-bottom:1px solid var(--bd);background:rgba(16,16,40,0.5);display:grid;grid-template-columns:1fr 1fr;gap:10px}
.trig-section{display:flex;flex-direction:column;gap:3px}
.trig-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--tx3);margin-bottom:4px}
.trig-item{font-size:10px;font-family:'JetBrains Mono';padding:3px 8px;border-radius:4px;color:var(--tx2)}
.trig-item.green{background:rgba(0,229,160,0.06);border-left:2px solid var(--ac)}
.trig-item.red{background:rgba(255,64,112,0.06);border-left:2px solid var(--rd)}
.trig-item b{color:var(--tx);font-weight:600}
.reeval-cell{display:inline-flex;align-items:center}
.reeval-badge{font-family:'Space Grotesk';font-size:10px;padding:5px 10px;border-radius:14px;border:1px solid;cursor:pointer;transition:all 0.15s;letter-spacing:0.2px}
.reeval-badge.pending{background:rgba(255,180,0,0.15);color:#ffb400;border-color:#ffb400;cursor:pointer;animation:reevalPulse 2s ease-in-out infinite}
.reeval-badge.pending:hover{background:rgba(255,180,0,0.3);transform:translateY(-1px)}
.reeval-badge.done{background:rgba(120,120,120,0.1);color:var(--tx3);border-color:var(--bd);cursor:default;font-size:9px}
@keyframes reevalPulse{0%,100%{opacity:1}50%{opacity:0.6}}
.reeval-menu{margin:6px 0 12px 18px;padding:10px 14px;background:rgba(255,180,0,0.06);border-left:3px solid #ffb400;border-radius:6px;display:flex;flex-direction:column;gap:8px}
.reeval-menu-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.btn-danger{background:rgba(255,64,112,0.1);color:#ff4070;border:1px solid #ff4070}
.btn-danger:hover{background:rgba(255,64,112,0.2)}
.triggers-empty{padding:8px 18px;font-size:10px;color:var(--tx3);font-style:italic;border-bottom:1px solid var(--bd);background:rgba(16,16,40,0.3)}
@media(max-width:900px){.triggers{grid-template-columns:1fr}}
.tag{display:inline-block;padding:1px 6px;border-radius:3px;font-size:8px;font-weight:700;text-transform:uppercase}
.tag-sell{background:var(--rdd);color:var(--rd)}.tag-info{background:var(--acd);color:var(--ac)}.tag-error{background:var(--rdd);color:var(--rd)}
.rules{padding:16px 18px}
.rule{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(30,30,74,0.3);font-size:12px}
.rule:last-child{border-bottom:none}.rule .k{color:var(--tx3)}.rule .v{font-family:'JetBrains Mono';font-weight:500;color:var(--ac)}.rule .v.red{color:var(--rd)}
.pbox{background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:14px;font-family:'JetBrains Mono';font-size:10px;line-height:1.6;color:var(--tx2);max-height:300px;overflow-y:auto;white-space:pre-wrap;margin:12px 18px 18px}
.btn{padding:8px 16px;border-radius:8px;border:1px solid var(--bd);background:var(--sf2);color:var(--tx2);font-family:'Space Grotesk';font-size:11px;font-weight:600;cursor:pointer;transition:all .15s}
.btn:hover{border-color:var(--ac);color:var(--ac);background:var(--acd)}.btn.d:hover{border-color:var(--rd);color:var(--rd)}
.ctrls{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:900px){.g2{grid-template-columns:1fr}}
.lr{padding:8px 18px;border-bottom:1px solid rgba(30,30,74,0.5);font-size:10px;display:grid;grid-template-columns:60px 50px 1fr;gap:8px;align-items:start}
.lr:hover{background:var(--sf2)}.lr:last-child{border-bottom:none}
.lr .lt{font-family:'JetBrains Mono';font-size:9px;color:var(--tx3)}.lr .ldd{color:var(--tx2);line-height:1.4}
.ll{background:var(--bg);border:1px solid var(--bd);border-radius:12px;overflow:hidden}
.ll .chd{background:var(--sf)}
.lc{height:280px;overflow-y:auto;padding:10px 14px;font-family:'JetBrains Mono';font-size:10px;line-height:1.7;scrollbar-width:thin}.lc::-webkit-scrollbar{width:3px}.lc::-webkit-scrollbar-thumb{background:var(--bd)}
.ll2{padding:1px 0}.ll2 .ts{color:var(--tx3)}.ll2 .INFO{color:var(--ac2)}.ll2 .WARNING{color:var(--am)}.ll2 .ERROR{color:var(--rd)}.ll2 .msg{color:var(--tx2)}
.emp{padding:40px;text-align:center;color:var(--tx3);font-size:11px}
footer{text-align:center;padding:20px;font-size:10px;color:var(--tx3)}
</style>
</head>
<body>
<nav><div class="nl"><div class="logo">P</div><div class="nt">Polymarket <span>Semi-Auto v3</span></div></div><div class="nr"><div class="lp"><div class="ld"></div>监控中</div><div class="rb" id="rb">30s</div></div></nav>
<div id="toast" class="toast"></div>
<div class="wrap">
<div class="ctrls">
<button class="btn" onclick="doAction('check')">🔍 检查持仓</button>
<button class="btn" onclick="doAction('refresh')">🔄 刷新</button>
<button class="btn" onclick="copyP()">📋 复制Prompt</button>
<button class="btn d" onclick="if(confirm('停止?'))doAction('stop')">⏹ 停止</button>
</div>
<div class="sl">🔍 市场扫描器</div>
<div class="card"><div class="chd"><h2>扫描Polymarket数据 → 生成Claude Research报告</h2></div>
<div class="tabs" style="padding:10px 18px 0;display:flex;gap:4px;border-bottom:1px solid var(--bd);margin-bottom:0">
<button class="tab tab-active" id="tab-kw" onclick="switchTab('kw')">🔍 关键词扫描</button>
<button class="tab" id="tab-tag" onclick="switchTab('tag')">🏷️ Tag扫描</button>
</div>

<div id="panel-kw" class="tab-panel">
<div style="padding:14px 18px 6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
<span style="font-size:10px;color:var(--tx3);margin-right:4px">快捷:</span>
<button class="chip" onclick="setKw('iran')">iran</button>
<button class="chip" onclick="setKw('israel')">israel</button>
<button class="chip" onclick="setKw('ukraine')">ukraine</button>
<button class="chip" onclick="setKw('russia')">russia</button>
<button class="chip" onclick="setKw('ceasefire')">ceasefire</button>
<button class="chip" onclick="setKw('taiwan')">taiwan</button>
<button class="chip" onclick="setKw('china')">china</button>
<button class="chip" onclick="setKw('north korea')">north korea</button>
<button class="chip" onclick="setKw('venezuela')">venezuela</button>
<button class="chip" onclick="setKw('election')">election</button>
<button class="chip" onclick="setKw('prime minister')">prime minister</button>
<button class="chip" onclick="setKw('parliament')">parliament</button>
<button class="chip" onclick="setKw('scotus')">scotus</button>
<button class="chip" onclick="setKw('fda approval')">fda approval</button>
<button class="chip" onclick="setKw('gpt')">gpt</button>
<button class="chip" onclick="setKw('agi')">agi</button>
<button class="chip" onclick="setKw('spacex')">spacex</button>
<button class="chip" onclick="setKw('oscar')">oscar</button>
<button class="chip" onclick="setKw('time person of the year')">time person of the year</button>
<button class="chip" onclick="setKw('nobel')">nobel</button>
</div>
<div style="padding:0 18px 14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
<input id="scanKw" placeholder="关键词 (如 iran, bitcoin, trump)" style="padding:8px 14px;border-radius:8px;border:1px solid var(--bd);background:var(--bg);color:var(--tx);font-family:'Space Grotesk';font-size:12px;width:260px">
<button class="btn" onclick="doScan('standard')">🚀 标准扫描</button>
<button class="btn" onclick="doScan('medium')">📊 中范围扫描</button>
<button class="btn" onclick="doScan('wide')">🌐 大范围扫描</button>
<button class="btn" onclick="copyScan()">📋 复制报告</button>
<button class="btn btn-primary" onclick="copyP()">🤖 复制给Claude</button>
<span id="scanStatus" style="font-size:11px;color:var(--tx3)"></span>
</div>
</div>

<div id="panel-tag" class="tab-panel" style="display:none">
<div style="padding:14px 18px 8px">
<div style="display:flex;gap:14px;align-items:center;margin-bottom:10px">
<span style="font-size:11px;color:var(--tx3);font-weight:600">范围:</span>
<label style="display:flex;align-items:center;gap:4px;font-size:11px;cursor:pointer"><input type="radio" name="tagMode" value="standard" checked style="cursor:pointer"> 标准</label>
<label style="display:flex;align-items:center;gap:4px;font-size:11px;cursor:pointer"><input type="radio" name="tagMode" value="medium" style="cursor:pointer"> 中范围</label>
<label style="display:flex;align-items:center;gap:4px;font-size:11px;cursor:pointer"><input type="radio" name="tagMode" value="wide" style="cursor:pointer"> 大范围</label>
<span style="font-size:10px;color:var(--tx3);margin-left:auto">点tag chip立即扫描</span>
</div>

<div style="margin-bottom:8px"><span style="font-size:10px;color:var(--ac);font-weight:600;letter-spacing:0.5px">TIER 1 重点 ⭐</span></div>
<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">
<button class="tag-chip tier1" onclick="doTagScan('Iran')">Iran</button>
<button class="tag-chip tier1" onclick="doTagScan('Israel')">Israel</button>
<button class="tag-chip tier1" onclick="doTagScan('Ukraine')">Ukraine</button>
<button class="tag-chip tier1" onclick="doTagScan('Ukraine Peace Deal')">Ukraine Peace Deal</button>
<button class="tag-chip tier1" onclick="doTagScan('Russia')">Russia</button>
<button class="tag-chip tier1" onclick="doTagScan('China')">China</button>
<button class="tag-chip tier1" onclick="doTagScan('Taiwan')">Taiwan</button>
<button class="tag-chip tier1" onclick="doTagScan('Geopolitics')">Geopolitics</button>
<button class="tag-chip tier1" onclick="doTagScan('Middle East')">Middle East</button>
<button class="tag-chip tier1" onclick="doTagScan('World')">World</button>
<button class="tag-chip tier1" onclick="doTagScan('Foreign Policy')">Foreign Policy</button>
</div>

<div style="margin-bottom:8px"><span style="font-size:10px;color:var(--ac2);font-weight:600;letter-spacing:0.5px">TIER 2 中等</span></div>
<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">
<button class="tag-chip tier2" onclick="doTagScan('Trump')">Trump</button>
<button class="tag-chip tier2" onclick="doTagScan('Trump Presidency')">Trump Presidency</button>
<button class="tag-chip tier2" onclick="doTagScan('SCOTUS')">SCOTUS</button>
<button class="tag-chip tier2" onclick="doTagScan('Politics')">Politics</button>
<button class="tag-chip tier2" onclick="doTagScan('US Politics')">US Politics</button>
<button class="tag-chip tier2" onclick="doTagScan('AI')">AI</button>
<button class="tag-chip tier2" onclick="doTagScan('OpenAI')">OpenAI</button>
<button class="tag-chip tier2" onclick="doTagScan('Tech')">Tech</button>
<button class="tag-chip tier2" onclick="doTagScan('Science')">Science</button>
<button class="tag-chip tier2" onclick="doTagScan('Venezuela')">Venezuela</button>
</div>

<div style="margin-bottom:8px"><span style="font-size:10px;color:var(--vi);font-weight:600;letter-spacing:0.5px">TIER 3 反向操作 (优先卖NO)</span></div>
<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">
<button class="tag-chip tier3" onclick="doTagScan('Awards')">Awards</button>
</div>

<div style="display:flex;gap:8px;align-items:center;padding-top:8px;border-top:1px solid var(--bd)">
<button class="btn" onclick="copyScan()">📋 复制报告</button>
<button class="btn btn-primary" onclick="copyP()">🤖 复制给Claude</button>
<span id="tagScanStatus" style="font-size:11px;color:var(--tx3)"></span>
</div>
</div>
</div>

<div class="pbox" id="scanReport" style="max-height:400px">点击扫描按钮拉取市场数据...</div>
</div>
</div>
<div class="ms">
<div class="m {{ 'g' if total_pnl >= 0 else 'r' }}"><div class="mi">💰</div><div class="ml">总盈亏</div><div class="mv" id="m-pnl" style="color:{{ '#00e5a0' if total_pnl >= 0 else '#ff4070' }}">${{ "%.2f"|format(total_pnl) }}</div><div class="msb">所有持仓</div></div>
<div class="m b"><div class="mi">📦</div><div class="ml">持仓数</div><div class="mv" id="m-count">{{ positions|length }}</div><div class="msb">活跃标的</div></div>
<div class="m v"><div class="mi">💵</div><div class="ml">总投入</div><div class="mv" id="m-cost">${{ "%.2f"|format(total_cost) }}</div><div class="msb">成本合计</div></div>
<div class="m g"><div class="mi">⏱</div><div class="ml">监控间隔</div><div class="mv">3m</div><div class="msb">自动检查</div></div>
</div>
<div class="sl">📦 持仓详情</div>
<div class="card"><div class="chd"><h2>当前持仓 (手动输入TP值)</h2><span class="cnt">{{ positions|length }}</span></div>
<div class="cb">
<div class="pos-hdr">
<span>名称</span><span>方向</span><span>入场价</span><span>当前价</span><span>成本$</span><span>现值$</span><span>份数</span><span>盈亏%</span><span>TP估值</span><span></span>
</div>
{% for p in positions %}
<div class="pos-row" data-asset="{{ p.asset }}">
<span class="nm">{{ p.title[:32] }}</span>
<span class="mono">{{ p.side }}</span>
<span class="mono">${{ "%.3f"|format(p.avg_price) }}</span>
<span class="mono cur-price">${{ "%.3f"|format(p.cur_price) }}</span>
<span class="mono" style="color:var(--tx3)">${{ "%.2f"|format(p.avg_price * p.size) }}</span>
<span class="mono cur-value" style="color:var(--tx2)">${{ "%.2f"|format(p.cur_price * p.size) }}</span>
<span class="mono" style="color:var(--tx3)">{{ "%.1f"|format(p.size) }}</span>
<span class="mono cur-pnl" style="color:{{ '#00e5a0' if p.pnl_pct >= 0 else '#ff4070' }}">{{ "%+.1f"|format(p.pnl_pct) }}%</span>
<div style="display:flex;align-items:center;gap:2px"><input type="number" step="1" min="0" max="100" class="tp-input" id="tp-{{ loop.index0 }}" placeholder="18" value="{{ (p.current_tp*100)|round|int if p.current_tp else '' }}" /><span style="font-size:10px;color:var(--tx3)">%</span></div>
<button class="btn-small" onclick="saveTP('{{ p.asset }}','{{ p.market_slug }}','{{ p.side }}',{{ p.avg_price }},{{ loop.index0 }},'{{ p.meta.end_date if p.meta else '' }}',{{ p.size }})">保存</button>
<span class="reeval-cell" data-asset="{{ p.asset }}">
{% if p.should_reeval %}
<button class="reeval-badge pending" onclick="toggleReevalMenu('{{ p.asset }}')">⚠️ 进度 {{ (p.progress_pct*100)|round|int }}% 重评 TP ▾</button>
{% elif p.reeval_status == 'done_uplift' %}
<span class="reeval-badge done">✓ 已重评 (上调至 {{ (p.reeval_new_tp*100)|round(1) }}%)</span>
{% elif p.reeval_status == 'done_skip' %}
<span class="reeval-badge done">已跳过重评</span>
{% elif p.reeval_status == 'done_close' %}
<span class="reeval-badge done">已重评清仓</span>
{% endif %}
</span>
</div>
{% if p.should_reeval %}
<div class="reeval-menu" id="reeval-menu-{{ p.asset }}" style="display:none">
<div class="reeval-menu-row">
<button class="btn-small" onclick="copyReevalPrompt('{{ p.asset }}')">📋 复制 Claude Prompt</button>
<span style="font-size:10px;color:var(--tx3);margin-left:8px">→ 粘贴到 Claude.ai Research</span>
</div>
<div class="reeval-menu-row">
<span style="font-size:11px;font-weight:600">A. 上调 TP 到</span>
<input type="number" step="1" min="0" max="99" class="tp-input" id="reeval-tp-{{ p.asset }}" placeholder="95" />
<span style="font-size:10px;color:var(--tx3)">%</span>
<button class="btn-small" onclick="markReeval('{{ p.asset }}','uplift')">✓ 应用</button>
</div>
<div class="reeval-menu-row">
<button class="btn-small" onclick="markReeval('{{ p.asset }}','skip')">B. 跳过 (维持原TP)</button>
<button class="btn-small btn-danger" onclick="markReeval('{{ p.asset }}','close')">C. 提前清仓</button>
</div>
</div>
{% endif %}
{% if p.triggers %}
<div class="triggers">
<div class="trig-section">
<span class="trig-label">📈 止盈触发价 (赚钱方向)</span>
{% if p.triggers.mode == "small_edge" %}
<span class="trig-item green">小edge单次平仓: <b>${{ "%.3f"|format(p.triggers.small_exit) }}</b> ({{ (p.triggers.small_exit*100)|round(1) }}%)</span>
{% else %}
<span class="trig-item green">T1 卖25% → <b>${{ "%.3f"|format(p.triggers.t1) }}</b> ({{ (p.triggers.t1*100)|round(1) }}%)</span>
<span class="trig-item green">T2 卖35% → <b>${{ "%.3f"|format(p.triggers.t2) }}</b> ({{ (p.triggers.t2*100)|round(1) }}%)</span>
<span class="trig-item green">T3 卖40% → <b>${{ "%.3f"|format(p.triggers.t3) }}</b> ({{ (p.triggers.t3*100)|round(1) }}%)</span>
{% endif %}
</div>
<div class="trig-section">
<span class="trig-label">📉 反向止损 (亏钱方向)</span>
<span class="trig-item red">W1 卖30% → <b>${{ "%.3f"|format(p.triggers.w1) }}</b> ({{ (p.triggers.w1*100)|round(1) }}%, 反{{ "%.1f"|format(p.triggers.w1_pp) }}pp)</span>
<span class="trig-item red">W2 卖40% → <b>${{ "%.3f"|format(p.triggers.w2) }}</b> ({{ (p.triggers.w2*100)|round(1) }}%, 反{{ "%.1f"|format(p.triggers.w2_pp) }}pp)</span>
<span class="trig-item red">W3 全平 → <b>${{ "%.3f"|format(p.triggers.w3) }}</b> ({{ (p.triggers.w3*100)|round(1) }}%, 反{{ "%.1f"|format(p.triggers.w3_pp) }}pp)</span>
</div>
</div>
{% else %}
<div class="triggers-empty">👉 填入TP估值后将显示具体止盈止损触发价</div>
{% endif %}
{% endfor %}
{% if not positions %}<div class="emp">暂无持仓</div>{% endif %}
</div></div>
<div class="g2"><div>
<div class="sl">📏 自动规则</div>
<div class="card"><div class="rules">
<div class="rule"><span class="k">止盈模式</span><span class="v">gap&lt;10pp走小edge / gap≥10pp走三档</span></div>
<div class="rule"><span class="k">小edge</span><span class="v">价≥mp+min(gap-2, 3~8pp) → 全平</span></div>
<div class="rule"><span class="k">止盈T1</span><span class="v">价≥mp+5pp → 卖原仓25%</span></div>
<div class="rule"><span class="k">止盈T2</span><span class="v">价≥mp+10pp → 卖原仓35%</span></div>
<div class="rule"><span class="k">止盈T3</span><span class="v">价≥mp+15pp (≤tp-2pp) → 剩余全平</span></div>
<div class="rule"><span class="k">反向止损1</span><span class="v red">反向 max(5, min(gap×0.33, 8))pp → 卖30%</span></div>
<div class="rule"><span class="k">反向止损2</span><span class="v red">反向 max(10, min(gap×0.67, 14))pp → 卖40%</span></div>
<div class="rule"><span class="k">反向止损3</span><span class="v red">反向 max(15, min(gap×1.0, 20))pp → 全平</span></div>
<div class="rule"><span class="k">时间止损</span><span class="v red">≤{{ time_stop_days }}天 且 偏移&lt;{{ (time_stop_pp*100)|int }}pp → 全平</span></div>
<div class="rule"><span class="k">检查频率</span><span class="v">每3分钟</span></div>
</div></div>
<div class="sl">📝 操作记录</div>
<div class="card"><div class="chd"><h2>事件</h2><span class="cnt">{{ events|length }}</span></div><div class="cb" style="max-height:200px">
{% for e in events %}<div class="lr"><div class="lt">{{ e.timestamp[5:16] }}</div><div><span class="tag tag-{{ e.event_type }}">{{ e.event_type }}</span></div><div class="ldd">{{ (e.market_slug or '')[:20] }} {{ (e.detail or '')[:50] }}</div></div>{% endfor %}
{% if not events %}<div class="emp">暂无</div>{% endif %}
</div></div>
</div><div>
<div class="sl">📋 Research Prompt</div>
<div class="card"><div class="chd"><h2>复制到Claude.ai</h2><button class="btn" onclick="copyP()" style="font-size:10px;padding:4px 12px">📋 复制</button></div><div class="pbox" id="pb">{{ prompt }}</div></div>
</div></div>
<div class="sl">🖥 实时日志</div>
<div class="ll"><div class="chd"><h2>Monitor Log</h2><div style="display:flex;gap:8px"><div class="lp" style="font-size:9px"><div class="ld"></div>3s</div><button class="btn" onclick="document.getElementById('lb').scrollTop=999999" style="font-size:10px;padding:4px 10px">↓</button></div></div><div class="lc" id="lb">Loading...</div></div>
</div>
<footer>Polymarket Semi-Auto v3</footer>
<textarea id="pt" style="position:absolute;left:-9999px">{{ prompt }}</textarea>
<script>
// 整页刷新已禁用 - 改用局部刷新
function syncSnapshot(){fetch('/api/snapshot').then(r=>r.json()).then(d=>{if(!d.ok)return;updateMetrics(d);updatePositions(d.positions||[])}).catch(e=>{})}
function updateMetrics(d){const el=(id)=>document.getElementById(id);if(el('m-pnl')){el('m-pnl').textContent='$'+d.total_pnl.toFixed(2);el('m-pnl').style.color=d.total_pnl>=0?'#00e5a0':'#ff4070'}if(el('m-count')){if(parseInt(el('m-count').textContent)!==d.position_count){location.reload();return}}if(el('m-cost'))el('m-cost').textContent='$'+d.total_cost.toFixed(2)}
function updatePositions(rows){rows.forEach(p=>{const row=document.querySelector(`[data-asset='${p.asset}']`);if(!row)return;const cp=row.querySelector('.cur-price');if(cp)cp.textContent='$'+p.cur_price.toFixed(3);const cv=row.querySelector('.cur-value');if(cv)cv.textContent='$'+p.value.toFixed(2);const pn=row.querySelector('.cur-pnl');if(pn){pn.textContent=(p.pnl_pct>=0?'+':'')+p.pnl_pct.toFixed(1)+'%';pn.style.color=p.pnl_pct>=0?'#00e5a0':'#ff4070'}});const rb=document.getElementById('rb');if(rb)rb.textContent='\u{2713} '+new Date().toLocaleTimeString().slice(0,5)}
syncSnapshot();setInterval(syncSnapshot,30000);
function fl(){fetch('/api/logs').then(r=>r.json()).then(d=>{if(!d.ok)return;const b=document.getElementById('lb');const a=b.scrollHeight-b.scrollTop-b.clientHeight<40;b.innerHTML=d.lines.map(l=>{let c='';if(l.includes('[INFO]'))c='INFO';else if(l.includes('[WARNING]'))c='WARNING';else if(l.includes('[ERROR]'))c='ERROR';return'<div class="ll2"><span class="ts">'+l.substring(0,19)+'</span> <span class="'+c+'">['+c+']</span> <span class="msg">'+l.substring(20).replace(/\[(?:INFO|WARNING|ERROR)\]\s?/,'')+'</span></div>'}).join('');if(a)b.scrollTop=b.scrollHeight})}
fl();setInterval(fl,3000);
function doAction(a){showT('ok',a==='check'?'检查中...':'...');fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a})}).then(r=>r.json()).then(d=>{showT(d.ok?'ok':'err',d.message);if(a==='refresh')setTimeout(syncSnapshot,800)}).catch(()=>showT('err','错误'))}
function showT(t,m){const e=document.getElementById('toast');e.className='toast '+t+' show';e.textContent=m;setTimeout(()=>e.classList.remove('show'),3000)}
function switchTab(name){
  const ids=['kw','tag'];
  ids.forEach(id=>{
    const tab=document.getElementById('tab-'+id);
    const panel=document.getElementById('panel-'+id);
    if(id===name){
      tab.classList.add('tab-active');
      panel.style.display='';
    }else{
      tab.classList.remove('tab-active');
      panel.style.display='none';
    }
  });
}

function doTagScan(tagLabel){
  const radios=document.querySelectorAll('input[name="tagMode"]');
  let mode='standard';
  for(const r of radios){if(r.checked){mode=r.value;break}}
  const startTs=Date.now()/1000;
  const modeLabel=mode==='wide'?'大范围':mode==='medium'?'中范围':'标准';
  document.getElementById('scanReport').textContent='🏷️ Tag扫描 ['+tagLabel+'] '+modeLabel+'模式 进行中...';
  const status=document.getElementById('tagScanStatus');
  if(status)status.textContent='⏳ 扫描中...';
  // chip flash
  const btns=document.querySelectorAll('.tag-chip');
  btns.forEach(b=>{
    if(b.textContent===tagLabel){
      // 根据tier类加对应flash
      if(b.classList.contains('tier1'))b.classList.add('flash-tier1');
      else if(b.classList.contains('tier2'))b.classList.add('flash-tier2');
      else if(b.classList.contains('tier3'))b.classList.add('flash-tier3');
      setTimeout(()=>{b.classList.remove('flash-tier1','flash-tier2','flash-tier3')},600);
    }
  });
  if(_scanPollTimer){clearInterval(_scanPollTimer);_scanPollTimer=null}
  fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'scan_tag',tag:tagLabel,mode:mode})})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showT('err',d.message);if(status)status.textContent='❌ '+d.message;return}
      showT('ok',d.message);
      pollScan(startTs,0);
    }).catch(()=>{showT('err','网络错误');if(status)status.textContent='❌ 网络错误'})
}

function setKw(kw){const el=document.getElementById('scanKw');el.value=kw;el.focus();const btns=document.querySelectorAll('.chip');btns.forEach(b=>{if(b.textContent===kw){b.classList.add('chip-flash');setTimeout(()=>b.classList.remove('chip-flash'),400)}})}
let _scanPollTimer=null;
function doScan(mode){
  mode = mode || 'standard';
  const kw=document.getElementById('scanKw').value;
  const startTs=Date.now()/1000;
  document.getElementById('scanReport').textContent = (mode==='wide'?'🌐 大范围扫描':mode==='medium'?'📊 中范围扫描':'🚀 标准扫描')+' 进行中,请等待...';
  document.getElementById('scanStatus').textContent='⏳ '+(mode==='wide'?'大范围扫描':mode==='medium'?'中范围扫描':'标准扫描')+'中...';
  if(_scanPollTimer){clearInterval(_scanPollTimer);_scanPollTimer=null}
  fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'scan',keyword:kw,mode:mode})})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showT('err',d.message);document.getElementById('scanStatus').textContent='❌ '+d.message;return}
      showT('ok',d.message);
      pollScan(startTs,0);
    }).catch(()=>{showT('err','请求错误');document.getElementById('scanStatus').textContent='❌ 网络错误'})
}
function pollScan(startTs,attempt){
  const MAX_ATTEMPTS=30;
  fetch('/api/scan_report').then(r=>r.json()).then(d=>{
    const elapsed=Math.floor(Date.now()/1000-startTs);
    if(d.ok&&d.mtime&&d.mtime>=startTs){
      document.getElementById('scanReport').textContent=d.report;
      document.getElementById('scanStatus').textContent='✅ 扫描完成 ('+elapsed+'秒) '+new Date().toLocaleTimeString();
      return;
    }
    if(attempt>=MAX_ATTEMPTS){
      document.getElementById('scanStatus').textContent='⚠️ 扫描超时(60秒), 请重试';
      return;
    }
    document.getElementById('scanStatus').textContent='⏳ 扫描中... '+elapsed+'秒';
    setTimeout(()=>pollScan(startTs,attempt+1),2000);
  }).catch(()=>setTimeout(()=>pollScan(startTs,attempt+1),2000))
}
function loadScan(){fetch('/api/scan_report').then(r=>r.json()).then(d=>{document.getElementById('scanReport').textContent=d.report;if(d.ok&&d.mtime){const dt=new Date(d.mtime*1000);document.getElementById('scanStatus').textContent='上次扫描: '+dt.toLocaleString()}}).catch(()=>{})}
function copyScan(){const t=document.getElementById('scanReport').textContent;navigator.clipboard.writeText(t).then(()=>showT('ok','报告已复制！粘贴到Claude Research'));if(!navigator.clipboard){const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');document.body.removeChild(a);showT('ok','报告已复制！')}}
loadScan();
async function copyP(){
  showT('ok','正在准备最新Prompt...');
  try{
    const r=await fetch('/api/full_prompt');
    const d=await r.json();
    if(!d.ok){showT('err','获取Prompt失败: '+(d.message||''));return}
    if(navigator.clipboard&&window.isSecureContext){
      await navigator.clipboard.writeText(d.prompt);
    }else{
      const a=document.createElement('textarea');
      a.value=d.prompt;a.style.position='fixed';a.style.left='-9999px';
      document.body.appendChild(a);a.select();document.execCommand('copy');document.body.removeChild(a);
    }
    showT('ok','✅ 最新Prompt已复制! 去Claude.ai粘贴');
  }catch(e){
    showT('err','复制失败: '+e.message);
  }
}
function toggleReevalMenu(asset){
  const m=document.getElementById('reeval-menu-'+asset);
  if(m)m.style.display=m.style.display==='none'?'':'none';
}

function copyReevalPrompt(asset){
  fetch('/api/reeval_prompt?token_id='+encodeURIComponent(asset))
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showT('err',d.message);return}
      navigator.clipboard.writeText(d.prompt)
        .then(()=>showT('ok','✓ 重评 Prompt 已复制 ('+d.prompt.length+' 字符)'))
        .catch(()=>showT('err','复制失败,请手动复制'));
    }).catch(()=>showT('err','拉取 prompt 失败'));
}

function markReeval(asset,action){
  let body={token_id:asset,action:action};
  if(action==='uplift'){
    const inp=document.getElementById('reeval-tp-'+asset);
    if(!inp||!inp.value){showT('err','请先填入新 TP 数字');return}
    const tpPct=parseFloat(inp.value);
    if(isNaN(tpPct)||tpPct<=0||tpPct>=100){showT('err','TP 必须是 0-100 之间的数字');return}
    body.new_tp=tpPct/100;
  }
  if(action==='close'){
    if(!confirm('确认提前清仓?\n\n注意:bot 不会自动卖,请你去 Polymarket 网页手动 sell。\n点确定后这条仓位会标记为"已重评清仓"。'))return;
  }
  fetch('/api/mark_reeval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showT('err',d.message);return}
      showT('ok',d.message);
      // 关菜单 + 1秒后整页刷新让徽章变灰
      const m=document.getElementById('reeval-menu-'+asset);
      if(m)m.style.display='none';
      setTimeout(()=>location.reload(),1200);
    }).catch(()=>showT('err','操作失败'));
}

function saveTP(tokenId,slug,side,entryPrice,idx,endDate,size){
  const tpVal=document.getElementById('tp-'+idx).value;
  if(!tpVal||isNaN(parseFloat(tpVal))){showT('err','请输入百分比 (1-99)');return}
  const tpPct=parseFloat(tpVal);
  if(tpPct<=0||tpPct>=100){showT('err','百分比必须在1-99之间');return}
  const tp=tpPct/100;
  fetch('/api/record_position',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    token_id:tokenId,slug:slug,side:side,entry_price:entryPrice,tp:tp,end_date:endDate,size:size
  })}).then(r=>r.json()).then(d=>{showT(d.ok?'ok':'err',d.message||'已保存 TP='+tpPct+'%')}).catch(()=>showT('err','保存失败'))
}
</script>
</body>
</html>
"""

def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        from modules.db import get_position_meta
        from modules.monitor import (TIER_1_MOVE_PP, TIER_2_MOVE_PP, TIER_3_MOVE_PP, TIER_3_MAX_NEAR_TP_PP,
            SMALL_EDGE_THRESHOLD_PP, SMALL_EDGE_MIN_MOVE_PP, SMALL_EDGE_MAX_TARGET_PP,
            WARNING1_GAP_RATIO, WARNING1_MIN_PP, WARNING1_MAX_PP,
            WARNING2_GAP_RATIO, WARNING2_MIN_PP, WARNING2_MAX_PP,
            WARNING3_GAP_RATIO, WARNING3_MIN_PP, WARNING3_MAX_PP)
        init_db()
        exe = Executor.get()
        positions = exe.get_positions()
        from datetime import datetime, timezone
        for p in positions:
            meta = get_position_meta(p["asset"])
            p["meta"] = meta or {}
            p["current_tp"] = (meta.get("new_tp") if meta and meta.get("new_tp") else (meta.get("tp") if meta else None))
            
            # 计算 reeval 相关字段
            p["reeval_status"] = (meta or {}).get("reeval_status") or "pending"
            p["reeval_new_tp"] = (meta or {}).get("reeval_new_tp")
            p["progress_pct"] = None
            p["days_left"] = None
            p["should_reeval"] = False
            
            cp = p.get("cur_price") or 0
            entry = (meta or {}).get("entry_price")
            tp_eff = p["current_tp"]
            if entry and tp_eff and tp_eff > entry:
                gap = tp_eff - entry
                if gap > 0:
                    p["progress_pct"] = max(0.0, min(1.0, (cp - entry) / gap))
            
            end_date = (meta or {}).get("end_date") or ""
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    p["days_left"] = (end_dt - datetime.now(timezone.utc)).days
                except Exception:
                    pass
            
            if (p["progress_pct"] is not None and p["progress_pct"] >= 0.80
                and p["days_left"] is not None and p["days_left"] >= 5
                and p.get("size", 0) > 0
                and p["reeval_status"] == "pending"):
                p["should_reeval"] = True
            
            # 计算触发价
            p["triggers"] = None
            if p["current_tp"] and meta:
                mp = meta["entry_price"]
                tp = meta.get("new_tp") or meta["tp"]
                gap_pp = (tp - mp) * 100
                is_yes = p["side"].upper() in ("YES", "Yes")
                # Polymarket: YES/NO持仓都是"token价格上涨=赚钱",方向统一
                # tp=用户对下注方向的真实概率估计=目标token价格
                # 止盈永远向上,止损永远向下
                
                triggers = {"is_yes": is_yes, "mp": mp, "tp": tp, "gap_pp": gap_pp}
                
                # 止盈(向上)
                if gap_pp < SMALL_EDGE_THRESHOLD_PP:
                    target_pp = min(gap_pp - 2, SMALL_EDGE_MAX_TARGET_PP)
                    target_pp = max(target_pp, SMALL_EDGE_MIN_MOVE_PP)
                    triggers["mode"] = "small_edge"
                    triggers["small_exit"] = mp + target_pp / 100
                else:
                    triggers["mode"] = "tiered"
                    triggers["t1"] = mp + TIER_1_MOVE_PP / 100
                    triggers["t2"] = mp + TIER_2_MOVE_PP / 100
                    t3_base = mp + TIER_3_MOVE_PP / 100
                    t3_cap = tp - TIER_3_MAX_NEAR_TP_PP / 100
                    triggers["t3"] = min(t3_base, t3_cap)
                
                # 反向止损三档(向下)
                w1_dist = max(WARNING1_MIN_PP, min(gap_pp * WARNING1_GAP_RATIO, WARNING1_MAX_PP)) / 100
                w2_dist = max(WARNING2_MIN_PP, min(gap_pp * WARNING2_GAP_RATIO, WARNING2_MAX_PP)) / 100
                w3_dist = max(WARNING3_MIN_PP, min(gap_pp * WARNING3_GAP_RATIO, WARNING3_MAX_PP)) / 100
                triggers["w1"] = mp - w1_dist
                triggers["w2"] = mp - w2_dist
                triggers["w3"] = mp - w3_dist
                triggers["w1_pp"] = w1_dist * 100
                triggers["w2_pp"] = w2_dist * 100
                triggers["w3_pp"] = w3_dist * 100
                
                p["triggers"] = triggers
        
        events = get_recent_events(30)
        total_pnl = sum((p["cur_price"]-p["avg_price"])*p["size"] for p in positions)
        total_cost = sum(p["avg_price"]*p["size"] for p in positions)
        # 尝试读取最新的扫描报告作为候选
        try:
            with open("last_scan.md", "r") as f:
                scan_content = f.read()
            prompt = DISCOVERY_PROMPT.replace("{positions_list}", scan_content)
        except:
            prompt = DISCOVERY_PROMPT.replace("{positions_list}", "(请先用扫描器生成候选市场列表)")
        return render_template_string(HTML, positions=positions, events=events, total_pnl=total_pnl, total_cost=total_cost, take_profit_rules=TAKE_PROFIT_RULES, time_stop_days=TIME_STOP_DAYS, time_stop_pp=TIME_STOP_MOVE_PP, prompt=prompt)

    @app.route("/api/control", methods=["POST"])
    def control():
        data = flask_request.get_json() or {}
        action = data.get("action","")
        if action == "check":
            if _monitor:
                threading.Thread(target=_monitor.check_once, daemon=True).start()
                return jsonify({"ok":True,"message":"持仓检查已触发"})
            return jsonify({"ok":False,"message":"Monitor未运行"})
        elif action == "refresh":
            return jsonify({"ok":True,"message":"已刷新"})
        elif action == "stop":
            if _monitor: _monitor.stop()
            import os,signal; os.kill(os.getpid(),signal.SIGTERM)
            return jsonify({"ok":True,"message":"停止中"})
        elif action == "scan":
            keyword = data.get("keyword", "")
            mode = data.get("mode", "standard")
            def do_scan():
                report = scan_and_report(keyword=keyword if keyword else None, include_orderbook=True, mode=mode)
                with open("last_scan.md", "w") as f:
                    f.write(report)
                from modules.db import log_event
                log_event("scan", keyword or "all", f"{len(report)} chars")
            threading.Thread(target=do_scan, daemon=True).start()
            return jsonify({"ok":True,"message":f"扫描启动: {keyword or '全部市场'}"})
        elif action == "scan_tag":
            tag = data.get("tag", "")
            mode = data.get("mode", "standard")
            if not tag:
                return jsonify({"ok":False,"message":"缺少tag参数"})
            from modules.scanner import scan_by_tag
            def do_tag_scan():
                report = scan_by_tag(tag, mode=mode)
                with open("last_scan.md", "w") as f:
                    f.write(report)
                from modules.db import log_event
                log_event("scan_tag", tag, f"mode={mode} {len(report)} chars")
            threading.Thread(target=do_tag_scan, daemon=True).start()
            return jsonify({"ok":True,"message":f"Tag扫描启动: {tag} ({mode})"})
        return jsonify({"ok":False,"message":"未知"})

    @app.route("/api/snapshot")
    def snapshot():
        """局部刷新接口: 返回持仓快照JSON"""
        try:
            exe = Executor.get()
            positions = exe.get_positions()
            rows = []
            total_pnl = 0.0
            total_cost = 0.0
            from modules.db import get_position_meta
            from datetime import datetime, timezone
            for p in positions:
                cp = p.get("cur_price") or 0
                ap = p.get("avg_price") or 0
                sz = p.get("size") or 0
                asset = p.get("asset", "")
                pnl_pct = ((cp - ap) / ap * 100) if ap > 0 else 0
                
                # 计算重评相关字段
                meta = get_position_meta(asset) or {}
                entry_price = meta.get("entry_price")
                effective_tp = meta.get("new_tp") or meta.get("tp")
                reeval_status = meta.get("reeval_status") or "pending"
                reeval_new_tp = meta.get("reeval_new_tp")
                
                progress_pct = None
                days_left = None
                should_reeval = False
                
                if entry_price and effective_tp and effective_tp > entry_price:
                    gap = effective_tp - entry_price
                    if gap > 0:
                        progress_pct = max(0.0, min(1.0, (cp - entry_price) / gap))
                
                # 距结算天数
                end_date = meta.get("end_date") or ""
                if end_date:
                    try:
                        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                        days_left = (end_dt - datetime.now(timezone.utc)).days
                    except Exception:
                        pass
                
                # 触发条件: 进度≥80% AND 距结算≥5天 AND size>0 AND status=pending
                if (progress_pct is not None and progress_pct >= 0.80
                    and days_left is not None and days_left >= 5
                    and sz > 0
                    and reeval_status == "pending"):
                    should_reeval = True
                
                rows.append({
                    "asset": asset,
                    "cur_price": cp,
                    "value": cp * sz,
                    "pnl_pct": pnl_pct,
                    "progress_pct": progress_pct,
                    "days_left": days_left,
                    "should_reeval": should_reeval,
                    "reeval_status": reeval_status,
                    "reeval_new_tp": reeval_new_tp,
                })
                total_pnl += (cp - ap) * sz
                total_cost += ap * sz
            return jsonify({
                "ok": True,
                "positions": rows,
                "total_pnl": total_pnl,
                "total_cost": total_cost,
                "position_count": len(rows),
            })
        except Exception as e:
            log.exception(f"snapshot error: {e}")
            return jsonify({"ok": False, "message": str(e)})

    @app.route("/api/reeval_prompt")
    def reeval_prompt_route():
        """生成某仓位的重评 prompt"""
        from modules.db import get_position_meta
        from modules.prompts import build_reeval_prompt
        from datetime import datetime, timezone
        token_id = flask_request.args.get("token_id", "")
        if not token_id:
            return jsonify({"ok": False, "message": "缺少 token_id"})
        meta = get_position_meta(token_id)
        if not meta:
            return jsonify({"ok": False, "message": "找不到该仓位元数据"})
        # 拉当前价
        try:
            exe = Executor.get()
            positions = exe.get_positions()
            cur_price = None
            for p in positions:
                if p.get("asset") == token_id:
                    cur_price = p.get("cur_price") or 0
                    break
            if cur_price is None:
                return jsonify({"ok": False, "message": "找不到该仓位的当前价"})
            
            # 距结算天数
            end_date = meta.get("end_date") or ""
            days_left = 0
            if end_date:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                days_left = (end_dt - datetime.now(timezone.utc)).days
            
            # 进度
            entry = meta.get("entry_price") or 0
            tp = meta.get("new_tp") or meta.get("tp") or 0
            gap = tp - entry
            progress = max(0.0, min(1.0, (cur_price - entry) / gap)) if gap > 0 else 0
            
            prompt = build_reeval_prompt(meta, cur_price, days_left, progress)
            return jsonify({"ok": True, "prompt": prompt, 
                            "market_slug": meta.get("market_slug", ""),
                            "tp": tp, "cur_price": cur_price})
        except Exception as e:
            log.exception(f"reeval_prompt error: {e}")
            return jsonify({"ok": False, "message": str(e)})

    @app.route("/api/mark_reeval", methods=["POST"])
    def mark_reeval_route():
        """标记重评结果. body: {token_id, action: uplift|skip|close, new_tp?}"""
        from modules.db import mark_reeval, log_event
        data = flask_request.get_json() or {}
        token_id = data.get("token_id", "")
        action = data.get("action", "")
        new_tp = data.get("new_tp")
        if not token_id or action not in ("uplift", "skip", "close"):
            return jsonify({"ok": False, "message": "参数错误"})
        if action == "uplift":
            if new_tp is None:
                return jsonify({"ok": False, "message": "uplift 必须提供 new_tp"})
            try:
                new_tp = float(new_tp)
                if not (0 < new_tp < 1):
                    return jsonify({"ok": False, "message": "new_tp 必须是 0-1 之间的小数"})
            except Exception:
                return jsonify({"ok": False, "message": "new_tp 格式错误"})
        ok = mark_reeval(token_id, action, new_tp=new_tp if action == "uplift" else None)
        if ok:
            log_event("reeval", token_id[:20], f"action={action} new_tp={new_tp}")
            msg_map = {
                "uplift": f"已上调 TP 到 {new_tp*100:.1f}%",
                "skip": "已跳过重评 (维持原 TP)",
                "close": "已标记重评清仓 (请去 Polymarket 网页手动卖出)"
            }
            return jsonify({"ok": True, "message": msg_map[action]})
        return jsonify({"ok": False, "message": "标记失败"})

    @app.route("/api/record_position", methods=["POST"])
    def record_position():
        from modules.db import save_position_meta
        data = flask_request.get_json() or {}
        try:
            entry_price = float(data["entry_price"])
            tp = float(data["tp"])
            side = data.get("side","YES")
            # Sanity check: TP必须高于持仓token买入价 (持有token涨=赚钱)
            if tp <= entry_price:
                return jsonify({
                    "ok": False,
                    "message": f"❌ TP方向错误! 你的{side}仓位买入价是{entry_price*100:.1f}%, "
                               f"TP({tp*100:.1f}%)必须>买入价。"
                               f"提醒: TP填的是你持仓token的目标价 (买NO就填NO的目标价)"
                })
            if tp >= 1.0:
                return jsonify({"ok": False, "message": "TP不能>=100%"})
            save_position_meta(
                token_id=data["token_id"],
                market_slug=data.get("slug",""),
                side=side,
                entry_price=entry_price,
                tp=tp,
                end_date=data.get("end_date",""),
                initial_size=float(data.get("size",0)),
                notes=data.get("notes","")
            )
            return jsonify({"ok":True,"message":"持仓元数据已记录"})
        except Exception as e:
            return jsonify({"ok":False,"message":str(e)})

    @app.route("/api/update_tp", methods=["POST"])
    def update_tp_api():
        from modules.db import update_tp, get_position_meta
        data = flask_request.get_json() or {}
        try:
            new_tp = float(data["new_tp"])
            token_id = data["token_id"]
            meta = get_position_meta(token_id)
            if meta:
                entry_price = meta.get("entry_price")
                if entry_price and new_tp <= entry_price:
                    return jsonify({
                        "ok": False,
                        "message": f"❌ TP方向错误! 持仓买入价{entry_price*100:.1f}%, "
                                   f"TP({new_tp*100:.1f}%)必须>买入价"
                    })
            if new_tp >= 1.0:
                return jsonify({"ok": False, "message": "TP不能>=100%"})
            update_tp(token_id, new_tp)
            return jsonify({"ok":True,"message":"tp已更新"})
        except Exception as e:
            return jsonify({"ok":False,"message":str(e)})

    @app.route("/api/full_prompt")
    def full_prompt():
        """返回最新的Prompt+扫描报告 (实时拼接)"""
        try:
            try:
                with open("last_scan.md", "r") as f:
                    scan_content = f.read()
            except:
                scan_content = "(请先用扫描器生成候选市场列表)"
            full = DISCOVERY_PROMPT.replace("{positions_list}", scan_content)
            return jsonify({"ok": True, "prompt": full})
        except Exception as e:
            log.exception(f"full_prompt error: {e}")
            return jsonify({"ok": False, "message": str(e)})

    @app.route("/api/scan_report")
    def scan_report():
        import os
        try:
            mtime = os.path.getmtime("last_scan.md")
            with open("last_scan.md", "r") as f:
                return jsonify({"ok":True, "report": f.read(), "mtime": mtime})
        except:
            return jsonify({"ok":False, "report": "暂无扫描报告。点击扫描按钮开始。", "mtime": 0})

    @app.route("/api/logs")
    def api_logs():
        try:
            r = subprocess.run(["tail","-80","bot.log"],capture_output=True,text=True,timeout=5)
            lines = r.stdout.strip().split("\n") if r.stdout else []
            filtered = [l for l in lines if "/api/" not in l and "GET / " not in l]
            return jsonify({"ok":True,"lines":filtered[-40:]})
        except:
            return jsonify({"ok":False,"lines":[]})

    return app
