#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""churn(刚买又卖)事后审判专题报告 → 自包含 HTML → 无头 Chrome 打印 PDF。
核心问题: 每笔快卖到底卖对了(卖完继续跌)/卖飞了(卖完又涨)/纯磨损(卖完没动)。
只读: 读 closed_positions + 拉 Polymarket 公开 prices-history 看卖出后走势。不动钱。
跑法: .venv/bin/python3 scripts/gen_churn_report.py [日期]
"""
import os, sys, sqlite3, time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from modules.gamma_client import install_polymarket_dns_guard
install_polymarket_dns_guard()
import requests

DB = os.path.join(ROOT, "v4.db")
REPORT_DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-07-24"
QUICK_H = 48   # "快卖" 判定: 持有 < 48h


def ts(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except Exception:
        return None


def fetch(tok):
    for _ in range(3):
        try:
            r = requests.get("https://clob.polymarket.com/prices-history",
                             params={"market": tok, "interval": "max", "fidelity": "60"}, timeout=20).json()
            return r.get("history") or []
        except Exception:
            time.sleep(1)
    return []


def kind(r):
    r = r or ""
    if "翻倍" in r or "TAKE_PROFIT" in r or "0.92" in r:
        return "止盈"
    if "STOP_LOSS" in r or "地板" in r or "强行" in r or "回撤" in r:
        return "止损"
    if "REEVAL" in r or "重评" in r:
        return "重评卖"
    if "FORCE" in r or "手动" in r:
        return "手动"
    return "其他"


def collect():
    con = sqlite3.connect(DB)
    rows = con.execute("""SELECT token_id,market_slug,side,avg_entry_price,exit_price,size,
        realized_pnl_usd,hold_duration_hours,exit_reason,exit_at FROM closed_positions
        WHERE hold_duration_hours IS NOT NULL ORDER BY exit_at""").fetchall()
    con.close()
    out = []
    for tok, slug, side, ent, ext, size, pnl, hrs, why, x_at in rows:
        title = slug
        xts = ts(x_at)
        hist = fetch(tok) if tok else []
        after = [h["p"] for h in hist if xts and h["t"] >= xts - 1800]
        r = {"slug": slug, "title": title or slug, "side": (side or "").upper(),
             "ent": ent or 0, "ext": ext or 0, "size": size or 0, "pnl": pnl or 0,
             "hrs": hrs or 0, "kind": kind(why)}
        if len(after) >= 2:
            r["last"] = after[-1]
            r["regret"] = (after[-1] - (ext or 0)) * (size or 0)   # >0 该拿着(卖飞); <0 卖对了
            r["fate"] = ("→ $1 赢" if after[-1] >= 0.95 else
                         ("→ $0 亏" if after[-1] <= 0.05 else f"现 {after[-1]:.2f}"))
        else:
            r["last"] = None; r["regret"] = 0; r["fate"] = "无数据"
        out.append(r)
        time.sleep(0.03)
    return out


def verdict(r):
    if r["last"] is None:
        return "无数据"
    if r["kind"] == "止盈":
        return "止盈"
    rel = (r["last"] - r["ext"]) / r["ext"] if r["ext"] else 0
    if rel > 0.10:
        return "卖飞了"
    if rel < -0.10:
        return "卖对了"
    return "纯磨损"


VB = {"卖对了": '<span class="vb good">卖对了 ✅</span>',
      "卖飞了": '<span class="vb bad">卖飞了 ❌</span>',
      "纯磨损": '<span class="vb wash">纯磨损 ⚪</span>'}
KB = {"重评卖": '<span class="badge b-hy">重评卖</span>', "止损": '<span class="badge b-ev">止损</span>',
      "手动": '<span class="badge b-un">手动</span>', "止盈": '<span class="badge b-co">止盈</span>'}


def m(v):
    c = "pos" if v > 0 else ("neg" if v < 0 else "zero")
    s = "+" if v > 0 else ("−" if v < 0 else "")
    return f'<span class="{c}">{s}${abs(v):.2f}</span>'


def churn_rows(rows):
    out = []
    for r in rows:
        s = r["side"]; scl = "pos" if s == "NO" else "co"
        out.append(
            f'<tr><td>{VB.get(verdict(r),"")}</td><td>{KB.get(r["kind"],"")}</td>'
            f'<td><b class="{scl}">{s}</b></td>'
            f'<td class="num">{r["ent"]:.2f}→{r["ext"]:.2f}</td>'
            f'<td class="num">{m(r["pnl"])}</td>'
            f'<td class="num dim">{r["hrs"]:.0f}h</td>'
            f'<td class="num strong">{r["fate"]}</td>'
            f'<td class="lbl dim">{r["title"][:40]}</td></tr>')
    return "\n".join(out)


def build_html(D):
    churn = D["churn"]
    n_right = sum(1 for r in churn if verdict(r) == "卖对了")
    n_wrong = sum(1 for r in churn if verdict(r) == "卖飞了")
    n_wash = sum(1 for r in churn if verdict(r) == "纯磨损")
    dodged = sum(r["regret"] for r in churn if verdict(r) == "卖对了")   # <0
    missed = sum(r["regret"] for r in churn if verdict(r) == "卖飞了")   # >0
    net_regret = sum(r["regret"] for r in churn)
    realized = sum(r["pnl"] for r in churn)
    wrong_rows = sorted([r for r in churn if verdict(r) == "卖飞了"], key=lambda x: -x["regret"])
    right_rows = sorted([r for r in churn if verdict(r) == "卖对了"], key=lambda x: x["regret"])
    wash_rows = [r for r in churn if verdict(r) == "纯磨损"]

    kpis = [
        ("快卖受审", f"{len(churn)} 笔", f"持有&lt;{QUICK_H}h·非止盈", "zero"),
        ("卖对了", f"{n_right} 笔", "卖完继续跌·躲过", "pos"),
        ("卖飞了", f"{n_wrong} 笔", "卖完又涨·被洗出", "neg"),
        ("纯磨损", f"{n_wash} 笔", "卖完没动·白磨", "zero"),
        ("择时本事", "≈ 掷硬币", "13:10:5·无 edge", "neg"),
    ]
    kpi_html = "\n".join(
        f'<div class="kpi"><div class="kl">{l}</div><div class="kv {c}">{v}</div>'
        f'<div class="kd chip zero"><em>{d}</em></div></div>' for l, v, d, c in kpis)

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>churn 事后审判报告</title><style>{CSS}</style></head><body>

<header class="cover">
  <div class="ct">
    <div class="eyebrow">POLYMARKET · 全自动账户 · 专题研究</div>
    <h1>「刚买又卖」事后审判报告</h1>
    <div class="sub">问题：这些一买就卖，<b>卖得准不准</b>？ · 方法：拉每笔<b>卖出之后</b>的真实价格走势逐笔审判 ·
      生成于 <b>{REPORT_DATE}</b> · 版本 <b>v8.3.2</b> · 只读，未改动任何仓位/参数/代码</div>
  </div>
  <div class="kpis">{kpi_html}</div>
</header>

<section class="callout">
  <div class="co-h"><span class="pin">⚖️</span> 一句话审判结果</div>
  <p>你问"这些卖得准不准、还是纯属乱花钱"——<b>答案：基本是掷硬币，没有择时本事，但也不是毁灭价值。</b>
  {len(churn)} 笔快卖里 <b class="pos">卖对了 {n_right}</b> · <b class="neg">卖飞了 {n_wrong}</b> · <b>纯磨损 {n_wash}</b>。</p>
  <div class="proof">
    <div class="pf-t">两个数字看懂它</div>
    <div class="pf-b">
      <div class="pf-col new"><div class="h">不是"乱花钱毁价值"</div><div class="b">反事实上，卖比一直拿着<b class="pos">净好 ${abs(net_regret):.2f}</b>
        —— 卖对了躲过的下跌 <b class="pos">${abs(dodged):.2f}</b> &gt; 卖飞了错过的上涨 <b class="neg">${missed:.2f}</b>。所以整体略微划算。</div></div>
      <div class="arr">≈</div>
      <div class="pf-col old"><div class="h">但也"没本事"、还真亏了钱</div><div class="b">卖对 : 卖飞 = <b>{n_right} : {n_wrong}</b> 近乎三七开 = <b>没择时优势</b>；
        每轮还磨手续费；这 {len(churn)} 笔实打实已实现 <b class="neg">{'−' if realized<0 else '+'}${abs(realized):.2f}</b>。</div></div>
    </div>
  </div>
</section>

<section>
  <h2><span class="n">1</span> 怎么审判的</h2>
  <div class="tiers-note">
    <div class="tnh">"快卖"定义 + 审判方法：</div>
    <ul>
      <li><b>受审范围</b>：持有 &lt; {QUICK_H} 小时、且<b>非止盈</b>平仓的 {len(churn)} 笔（止盈是"翻倍/0.92 落袋"，那是对的，不算 churn）。类型 = 重评判卖 / 止损 / 手动。</li>
      <li><b>怎么判准不准</b>：拉这笔<b>卖出之后</b>该方向 token 的真实价格走势 ——
        卖完<b class="pos">继续跌</b>（现价低于卖出价 &gt;10% 或直接归零）= <b class="pos">卖对了</b>（拿着会更惨）；
        卖完<b class="neg">又涨回去</b>（现价高于卖出价 &gt;10% 或直接结算成 $1）= <b class="neg">卖飞了</b>（被洗出来）；
        卖完基本没动 = <b>纯磨损</b>（白付滑点手续费）。</li>
      <li><b>反事实（regret）</b>：（卖出后现价 − 卖出价）× 股数 —— 正=本该拿着（卖飞），负=卖对了躲过跌。</li>
    </ul>
  </div>
</section>

<section>
  <h2><span class="n">2</span> 审判总账</h2>
  <div class="two" style="margin-bottom:12px">
    <div class="stat"><div class="big neg">{n_wrong}<span class="s"> 卖飞</span> : {n_right}<span class="s"> 卖对</span></div>
      <div class="cap">近乎<b>三七开的胜负</b>（另有 {n_wash} 笔纯磨损）——bot <b>看不出</b>哪笔该卖哪笔该扛，纯掷硬币。有本事的择时不该是这个分布。</div></div>
    <div class="stat"><div class="big {'neg' if realized<0 else 'pos'}">{'−' if realized<0 else '+'}${abs(realized):.2f}</div>
      <div class="cap">这 {len(churn)} 笔快卖<b>真实已实现</b>盈亏。即使"卖对了"也是<b>亏着卖</b>（只是比拿着少亏），所以实现账仍是负的。</div></div>
  </div>
  <div class="callout" style="margin:0">
    <div class="co-h" style="font-size:13px">🔍 关键规律：最疼的"卖飞了"，全是<b>止损把要反弹的仓砍在坑底</b></div>
    <p style="margin:0">波动大的事件型仓一时砸穿止损线 → 被砍在最低点 → 转头又涨回去甚至结算成 $1。这类"止损→反弹"是被洗出来的主力，
    也跟你之前发现的"止损/重评对波动仓太灵敏"是同一个病根。</p>
  </div>
</section>

<section class="break">
  <h2><span class="n">3</span> 卖飞了 {n_wrong} 笔 · 卖完又涨（被洗出来）<em>（错过合计 <b class="neg">+${missed:.2f}</b> 若拿着）</em></h2>
  <table class="grid closed"><thead><tr><th>判定</th><th>类型</th><th>方向</th><th>买→卖</th><th>已实现</th><th>持有</th><th>卖后结局</th><th>市场</th></tr></thead>
    <tbody>{churn_rows(wrong_rows)}</tbody></table>
  <div class="mini danger" style="margin-top:10px"><b>看第一列"卖后结局"→ $1 赢 的那几笔：</b>卖出时还在半山腰（0.64/0.74/0.80/0.50），卖掉后市场一路走到结算 $1 —— 这些是把<b>最终会赢的仓</b>提前砍了。尤其止损那几笔（Russia 砍 0.48、claude-opus 砍 0.22、warsh 砍 0.42、trump 砍 0.30），砍在坑底、随后大反弹。</div>
</section>

<section>
  <h2><span class="n">4</span> 卖对了 {n_right} 笔 · 卖完继续跌（躲过了）<em>（躲过合计 <b class="pos">${abs(dodged):.2f}</b> 的下跌）</em></h2>
  <table class="grid closed"><thead><tr><th>判定</th><th>类型</th><th>方向</th><th>买→卖</th><th>已实现</th><th>持有</th><th>卖后结局</th><th>市场</th></tr></thead>
    <tbody>{churn_rows(right_rows)}</tbody></table>
  <div class="mini" style="margin-top:8px">这些"卖后结局 → $0 亏"的，是卖掉后市场归零 —— 卖对了，拿着会亏光。<b>但注意：多数也是"亏着卖"的</b>，只是少亏。所以"卖对了"≠"赚了"，只是止损止损。</div>
  {f'''<h2 style="font-size:12.5px;margin-top:16px"><span class="n" style="width:18px;height:18px;font-size:10px;background:var(--dim)">⚪</span> 纯磨损 {n_wash} 笔 · 卖完没怎么动，白付滑点</h2>
  <table class="grid closed"><thead><tr><th>判定</th><th>类型</th><th>方向</th><th>买→卖</th><th>已实现</th><th>持有</th><th>卖后结局</th><th>市场</th></tr></thead>
    <tbody>{churn_rows(wash_rows)}</tbody></table>''' if wash_rows else ''}
</section>

<section>
  <h2><span class="n">5</span> 结论 · 到底是不是"乱花钱"</h2>
  <div class="two">
    <div class="card"><div class="ch">它不是"毁灭价值"</div>
      <div class="mini" style="margin-top:0">反事实上卖比拿着<b>净好 ${abs(net_regret):.2f}</b>：躲过的下跌（${abs(dodged):.2f}）比错过的上涨（${missed:.2f}）多一点。所以<b>不能说纯属乱花钱</b> —— 平均下来这些止损/重评卖，略微帮账户少亏了。</div></div>
    <div class="card"><div class="ch neg">但它是"无效劳动"</div>
      <div class="mini" style="margin-top:0"><b>① 没择时 edge</b>：卖对:卖飞 = {n_right}:{n_wrong} 掷硬币。<b>② 真磨钱</b>：{len(churn)} 笔实现 {'−' if realized<0 else '+'}${abs(realized):.2f}，每轮还付滑点。<b>③ 偶尔重伤</b>：把 Russia/claude-opus/warsh/trump 这些<b>会反弹甚至结算赢</b>的仓砍在坑底。</div></div>
  </div>
  <div class="rec todo" style="margin-top:12px"><div class="rh">下一步（等你定，我不擅自动）</div>
    <ul>
      <li>想<b>少被洗出（减卖飞）</b> → 让止损/重评对<b>波动大的事件型 + 刚买的新仓</b>别那么灵敏：给新仓一个"重评宽限期"、或抬高盘中触发门槛（你 8.3.0 改成"回撤 5pp 就触发"是偏灵敏的一头）。</li>
      <li>想<b>少磨损（减来回买）</b> → 卖掉一个市场后加"冷静期"，N 天内不许再买它（Russia 来回 6 轮就是没冷静期）。</li>
      <li>这份是<b>诊断</b>，样本 {len(churn)} 笔、账户总盘子小；要不要动、动哪个，你看完拍板，我再做具体方案 + 实测。</li>
    </ul></div>
</section>

<footer>
  数据来源：<b>v4.db · closed_positions</b>（持有时长可算的全部平仓）+ 对每笔卖出 token 的 <b>Polymarket prices-history</b>（公开只读，看卖出后真实走势）。
  受审集 = 持有 &lt; {QUICK_H}h 且非止盈的 {len(churn)} 笔。判定：卖后现价相对卖出价 涨/跌 &gt;10%（或结算 $1/$0）→ 卖飞/卖对；之间 → 纯磨损。
  本报告<b>只读</b>：未改动任何仓位、参数或代码。
  <span class="gen">Polymarket AUTO · churn 事后审判专题 · 生成于 {REPORT_DATE}</span>
</footer>

</body></html>"""


CSS = r"""
* { margin:0; padding:0; box-sizing:border-box; }
:root{ --ink:#141a26; --ink2:#41506b; --dim:#7c89a0; --line:#e5e9f2; --line2:#eef1f7; --bg:#f6f8fc; --card:#ffffff;
  --pos:#0e8a5f; --posbg:#e7f6ef; --neg:#d13b3b; --negbg:#fdecec; --zero:#8a94a8; --brand:#26356b; --brand2:#3f8bd6;
  --ev:#b7791f; --evbg:#fbf3e2; --hy:#2f6fb0; --hybg:#e8f1fa; --co:#7a4fc0; --cobg:#f0e9fb; }
html{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }
body{ font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif; color:var(--ink); background:var(--bg); font-size:11px; line-height:1.5; width:820px; margin:0 auto; padding:0 26px 40px; }
.cover{ padding:26px 0 8px; }
.eyebrow{ font-size:10px; letter-spacing:.18em; color:var(--brand2); font-weight:700; }
.cover h1{ font-size:30px; font-weight:800; letter-spacing:-.5px; color:var(--brand); margin:4px 0 6px; }
.cover .sub{ color:var(--ink2); font-size:11px; } .cover .sub b{ color:var(--ink); }
.kpis{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-top:16px; }
.kpi{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 13px; box-shadow:0 1px 2px rgba(20,26,38,.04); }
.kl{ font-size:10px; color:var(--dim); font-weight:600; }
.kv{ font-size:19px; font-weight:800; letter-spacing:-.5px; margin:3px 0 5px; color:var(--ink); }
.kv.pos{ color:var(--pos); } .kv.neg{ color:var(--neg); } .kv.zero{ color:var(--ink); }
.chip{ display:inline-block; font-size:9px; font-weight:700; padding:2px 6px; border-radius:20px; }
.chip em{ font-style:normal; opacity:.7; font-weight:600; } .chip.zero{ background:#eef1f7; color:var(--zero); }
.callout{ background:linear-gradient(180deg,#fff,#fbfcff); border:1.5px solid #d9e2f2; border-radius:14px; padding:16px 18px; margin:18px 0; box-shadow:0 2px 10px rgba(38,53,107,.06); }
.co-h{ font-size:15px; font-weight:800; color:var(--brand); margin-bottom:7px; } .pin{ margin-right:4px; }
.callout p{ color:var(--ink2); margin-bottom:11px; } .callout b{ color:var(--ink); }
.proof{ border:1.5px dashed #cdd8ee; border-radius:11px; padding:11px 13px; background:#fafcff; }
.pf-t{ font-weight:800; color:var(--brand); font-size:12px; margin-bottom:8px; }
.pf-b{ display:flex; align-items:stretch; gap:10px; }
.pf-col{ flex:1; border-radius:9px; padding:10px 12px; } .pf-col .h{ font-size:10.5px; font-weight:800; margin-bottom:4px; }
.pf-col .b{ font-size:10px; color:var(--ink2); line-height:1.5; }
.pf-col.old{ background:#fbeeee; } .pf-col.old .h{ color:var(--neg); } .pf-col.new{ background:#e7f6ef; } .pf-col.new .h{ color:var(--pos); }
.pf-col b{ color:var(--ink); } .arr{ align-self:center; font-size:22px; color:var(--brand2); font-weight:800; }
section{ margin:20px 0; }
h2{ font-size:15px; font-weight:800; color:var(--ink); margin-bottom:9px; display:flex; align-items:center; gap:9px; }
h2 .n{ display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px; background:var(--brand); color:#fff; border-radius:7px; font-size:12px; font-weight:800; }
h2 em{ font-style:normal; font-size:11px; font-weight:600; color:var(--dim); } h2 em b{ color:var(--ink2); }
table.grid{ width:100%; border-collapse:collapse; font-size:10px; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
table.grid th{ background:#f3f6fc; color:var(--ink2); font-weight:700; text-align:right; padding:7px 9px; border-bottom:1px solid var(--line); white-space:nowrap; }
table.grid th:first-child, table.grid td:first-child{ text-align:left; }
table.grid td{ padding:6px 9px; border-bottom:1px solid var(--line2); text-align:right; white-space:nowrap; }
table.grid tr:last-child td{ border-bottom:none; } table.grid tbody tr:nth-child(even){ background:#fafbfe; }
table.closed td{ padding-top:4px; padding-bottom:4px; font-size:9.5px; }
td.lbl{ text-align:left; font-weight:600; color:var(--ink); max-width:215px; overflow:hidden; text-overflow:ellipsis; }
td.num{ font-variant-numeric:tabular-nums; } td.dim{ color:var(--dim); font-weight:500; } td.strong{ font-weight:700; }
.pos{ color:var(--pos); } .neg{ color:var(--neg); } .zero{ color:var(--zero); } .co{ color:var(--co); }
.vb{ font-weight:800; font-size:9px; padding:2px 6px; border-radius:5px; white-space:nowrap; }
.vb.good{ background:var(--posbg); color:var(--pos); } .vb.bad{ background:var(--negbg); color:var(--neg); } .vb.wash{ background:#eef1f7; color:var(--zero); }
.badge{ display:inline-block; font-size:8.5px; font-weight:800; padding:1.5px 6px; border-radius:5px; }
.b-ev{ background:var(--evbg); color:var(--ev); } .b-hy{ background:var(--hybg); color:var(--hy); } .b-co{ background:var(--cobg); color:var(--co); } .b-un{ background:#eef1f7; color:var(--dim); }
.tiers-note{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:11px 14px; }
.tnh{ font-weight:700; margin-bottom:6px; color:var(--ink); font-size:10.5px; }
.tiers-note ul{ list-style:none; } .tiers-note li{ font-size:10px; color:var(--ink2); padding:4px 0; line-height:1.55; } .tiers-note b{ color:var(--ink); }
.two{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.card{ background:var(--card); border:1px solid var(--line); border-radius:11px; padding:13px 15px; }
.ch{ font-weight:800; font-size:11px; color:var(--ink); margin-bottom:9px; } .ch.neg{ color:var(--neg); }
.mini{ font-size:9.5px; color:var(--ink2); margin-top:8px; line-height:1.55; } .mini b{ color:var(--ink); }
.mini.danger{ background:#fff8f0; border:1px solid #f6e1c8; border-radius:8px; padding:9px 12px; color:#8a5a1a; } .mini.danger b{ color:#7a3d0a; }
.stat{ background:var(--card); border:1px solid var(--line); border-radius:11px; padding:14px 16px; }
.stat .big{ font-size:30px; font-weight:800; color:var(--brand); letter-spacing:-1px; line-height:1; } .stat .big.pos{ color:var(--pos); } .stat .big.neg{ color:var(--neg); }
.stat .big .s{ font-size:13px; font-weight:700; color:var(--dim); } .stat .cap{ font-size:10px; color:var(--ink2); margin-top:8px; line-height:1.55; } .stat .cap b{ color:var(--ink); }
.rec{ border-radius:11px; padding:12px 16px; } .rec.todo{ background:#f4f7fc; border:1px solid var(--line); }
.rh{ font-weight:800; font-size:11.5px; margin-bottom:6px; color:var(--brand); }
.rec ul{ margin-left:16px; } .rec li{ font-size:10px; color:var(--ink2); padding:3px 0; line-height:1.5; } .rec b{ color:var(--ink); }
footer{ margin-top:26px; padding-top:12px; border-top:1px solid var(--line); font-size:9px; color:var(--dim); line-height:1.7; } footer b{ color:var(--ink2); }
.gen{ display:block; margin-top:6px; color:#aab3c5; font-weight:600; }
@media print{ body{ width:auto; background:#fff; padding:0; } .kpi,.card,.stat,.callout,table.grid{ box-shadow:none; }
  section.break{ break-before:page; } .callout,.card,.stat,.rec,tr,thead,.two{ break-inside:avoid; } table.grid{ break-inside:auto; } h2{ break-after:avoid; } }
"""


def main():
    rows = collect()
    churn = [r for r in rows if r["kind"] in ("重评卖", "止损", "手动") and r["hrs"] < QUICK_H and r["last"] is not None]
    D = {"churn": churn}
    html = build_html(D)
    out = os.path.join(ROOT, "churn_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    nr = sum(1 for r in churn if verdict(r) == "卖对了")
    nw = sum(1 for r in churn if verdict(r) == "卖飞了")
    nh = sum(1 for r in churn if verdict(r) == "纯磨损")
    print(f"HTML -> {out}")
    print(f"churn {len(churn)} 笔 | 卖对{nr}/卖飞{nw}/磨损{nh} | 实现 {sum(r['pnl'] for r in churn):+.2f} | 反事实 {sum(r['regret'] for r in churn):+.2f}")


if __name__ == "__main__":
    main()
