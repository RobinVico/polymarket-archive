#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试仓 (Paper) 专题研究报告 → 自包含 HTML → 无头 Chrome 打印成 PDF。
只读 v4.db 的 paper_positions;不动钱、不改仓、不调 API。复用 gen_run_report.py 的视觉。
跑法: .venv/bin/python3 scripts/gen_paper_report.py [报告日期]
"""
import os, sys, sqlite3
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "v4.db")
REPORT_DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-07-21"


def money(v, plus=True):
    if v is None:
        return '<span class="zero">—</span>'
    c = "pos" if v > 0 else ("neg" if v < 0 else "zero")
    sign = ("+" if v > 0 else ("−" if v < 0 else ""))
    return f'<span class="{c}">{sign}${abs(v):.2f}</span>'


def why_paper(entry):
    if entry <= 0.40:
        return ("太便宜 ≤$0.40", "cheap")
    if entry >= 0.85:
        return ("太贵 ≥$0.85", "exp")
    return ("黑名单/其他", "bl")


def short_reason(r):
    if not r:
        return '<span class="dim">仍在跑</span>'
    if "翻倍" in r:
        return '<span class="pos">翻倍先到·全卖 🚀</span>'
    if "0.92" in r:
        return '<span class="pos">0.92·卖一半</span>'
    if "强行止损" in r or "-50%" in r or "−50%" in r:
        return '<span class="neg">−50% 强平</span>'
    if "地板" in r:
        return '<span class="neg">$0.05 地板</span>'
    if "移动止损" in r or "回撤" in r:
        return '<span class="neg">回撤止损</span>'
    return r[:18]


TIER_BADGE = {
    "event_driven": '<span class="badge b-ev">事件</span>',
    "hybrid": '<span class="badge b-hy">综合</span>',
    "convergent": '<span class="badge b-co">收敛</span>',
}


def collect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM paper_positions ORDER BY created_at, id").fetchall()]
    con.close()
    for r in rows:
        r["wpnl"] = r["would_sell_pnl_usd"]
        r["reason_short"] = short_reason(r["would_sell_reason"])
        r["why"], r["whycls"] = why_paper(r["entry_price"] or 0)
    wins = [r for r in rows if r["wpnl"] is not None and r["wpnl"] > 0]
    loss = [r for r in rows if r["wpnl"] is not None and r["wpnl"] < 0]
    openp = [r for r in rows if r["wpnl"] is None]
    closed = wins + loss
    D = {
        "rows": rows, "wins": sorted(wins, key=lambda x: -x["wpnl"]),
        "loss": sorted(loss, key=lambda x: x["wpnl"]), "open": openp,
        "n": len(rows), "n_closed": len(closed),
        "net": sum(r["wpnl"] for r in closed),
        "win_sum": sum(r["wpnl"] for r in wins),
        "loss_sum": sum(r["wpnl"] for r in loss),
        "win_rate": (len(wins) / len(closed) * 100) if closed else 0,
        "avg_win": (sum(r["wpnl"] for r in wins) / len(wins)) if wins else 0,
        "avg_loss": (sum(r["wpnl"] for r in loss) / len(loss)) if loss else 0,
        "cheap": [r for r in rows if (r["entry_price"] or 0) <= 0.40],
        "exp": [r for r in rows if (r["entry_price"] or 0) >= 0.85],
        "n_yes": sum(1 for r in rows if (r["side"] or "").lower() == "yes"),
        "n_no": sum(1 for r in rows if (r["side"] or "").lower() == "no"),
        "n_ev": sum(1 for r in rows if r["stop_loss_tier"] == "event_driven"),
        "n_co": sum(1 for r in rows if r["stop_loss_tier"] == "convergent"),
        "first": min(r["created_at"] for r in rows)[:10],
        "last": max(r["created_at"] for r in rows)[:10],
    }
    D["bl"] = [r for r in rows if 0.40 < (r["entry_price"] or 0) < 0.85]
    return D


def side_price(r):
    s = (r["side"] or "").upper()
    cl = "pos" if s == "NO" else "co"
    return f'<b class="{cl}">{s}</b> @{r["entry_price"]:.2f}'


def win_rows(rows):
    out = []
    for r in rows:
        out.append(
            f'<tr><td class="num strong">{money(r["wpnl"])}</td>'
            f'<td>{side_price(r)}</td><td class="num dim">${r["size_usd"]:.1f}</td>'
            f'<td>{TIER_BADGE.get(r["stop_loss_tier"],"")}</td>'
            f'<td class="lbl">{r["reason_short"]}</td>'
            f'<td class="lbl dim">{(r["title"] or r["market_slug"])[:44]}</td></tr>')
    return "\n".join(out)


def loss_rows(rows):
    out = []
    for r in rows:
        out.append(
            f'<tr><td class="num strong">{money(r["wpnl"])}</td>'
            f'<td>{side_price(r)}</td><td class="num dim">${r["size_usd"]:.1f}</td>'
            f'<td>{TIER_BADGE.get(r["stop_loss_tier"],"")}</td>'
            f'<td class="lbl">{r["reason_short"]}</td>'
            f'<td class="lbl dim">{(r["title"] or r["market_slug"])[:44]}</td></tr>')
    return "\n".join(out)


def open_rows(rows):
    out = []
    for r in rows:
        cur = f'{r["cur_price"]:.2f}' if r["cur_price"] else "—"
        why_chip_cls = "neg" if r["whycls"] == "exp" else "zero"
        out.append(
            f'<tr><td>{side_price(r)}</td><td class="num dim">${r["size_usd"]:.1f}</td>'
            f'<td>{TIER_BADGE.get(r["stop_loss_tier"],"")}</td>'
            f'<td><span class="chip {why_chip_cls}">{r["why"]}</span></td>'
            f'<td class="num dim">{cur}</td>'
            f'<td class="lbl dim">{(r["title"] or r["market_slug"])[:42]}</td></tr>')
    return "\n".join(out)


def build_html(D):
    kpis = [
        ("累计测试仓", f"{D['n']} 仓", "从 07-08 至今", "zero"),
        ("模拟净盈亏", f"{'+' if D['net']>=0 else '−'}${abs(D['net']):.2f}", "18 仓已了结", "pos" if D["net"] > 0 else "neg"),
        ("模拟胜率", f"{D['win_rate']:.0f}%", f"{len(D['wins'])} 赢 / {len(D['loss'])} 亏", "zero"),
        ("仍在跑", f"{len(D['open'])} 仓", "还没触发卖点", "zero"),
        ("能否真下单", "不能", "物理隔离·需新代码", "neg"),
    ]
    kpi_html = "\n".join(
        f'<div class="kpi"><div class="kl">{l}</div><div class="kv {c}">{v}</div>'
        f'<div class="kd chip zero"><em>{d}</em></div></div>'
        for l, v, d, c in kpis)

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>测试仓研究报告</title><style>{CSS}</style></head><body>

<header class="cover">
  <div class="ct">
    <div class="eyebrow">POLYMARKET · 全自动账户 · 专题研究</div>
    <h1>测试仓 (Paper) 研究报告</h1>
    <div class="sub">从项目上线到现在的<b>全部测试仓</b> · 数据区间 <b>{D['first']} ~ {D['last']}</b> ·
      生成于 <b>{REPORT_DATE}</b> · 版本 <b>v8.3.2</b> · 本报告只读，未改动任何仓位/参数/代码</div>
  </div>
  <div class="kpis">{kpi_html}</div>
</header>

<section class="callout">
  <div class="co-h"><span class="pin">📌</span> 一句话结论（先看这个）</div>
  <p><b>测试仓 = 被「0.40–0.85 分流规则」挡在门外的 GLM 选品。</b>共 {D['n']} 条里，<b>{len(D['cheap'])} 条是"太便宜"（≤$0.40 的冷门票）</b>、{len(D['exp'])} 条是"太贵"（≥$0.85 近乎板上钉钉）、黑名单 {len(D['bl'])} 条。它们全是模型看上、但规则判定"不值得动真金"的票。</p>
  <div class="proof">
    <div class="pf-t">你最想知道的两件事</div>
    <div class="pf-b">
      <div class="pf-col old"><div class="h">测试仓能真金下单吗？</div><div class="b"><b class="neg">现在不能。</b>物理隔离（代码级、独立数据表、干跑函数只写库），<b>没有任何"转真买"的按钮/接口/开关</b>；要让它下单得<b>写新代码</b>，不是翻个设置。（详见 §2）</div></div>
      <div class="arr">→</div>
      <div class="pf-col new"><div class="h">那这些被拒的票表现如何？</div><div class="b">反直觉：模拟跑下来 <b class="pos">净赚 {'+' if D['net']>=0 else '−'}${abs(D['net']):.2f}</b>，胜率只有 <b>{D['win_rate']:.0f}%</b> 却赚钱 —— 靠"赢家翻倍、输家封顶"的不对称。值不值得放开，§4–§5 摊开讲（有硬 caveat）。</div></div>
    </div>
  </div>
</section>

<section>
  <h2><span class="n">1</span> 测试仓是什么 · 怎么进去的</h2>
  <div class="tiers-note">
    <div class="tnh">分流规则（写死，`auto_discovery.route_of`）——按<b>执行时刻的新鲜盘口价</b> p 判，不是推荐价：</div>
    <ul>
      <li><b class="pos">0.40 &lt; p &lt; 0.85 → 真买</b>（走 sizing 公式动真金）。</li>
      <li><b class="neg">否则 → 测试仓</b>：p ≤ $0.40（太便宜/冷门）、p ≥ $0.85（太贵/近乎确定）、边界值、或价格拿不到（fail-safe）。</li>
      <li><b class="neg">关键词黑名单命中 → 强制测试仓</b>（bitcoin/eth/cpi/inflation 等，无视价格）。</li>
      <li>宇宙闸门对测试仓<b>照样生效</b>：非白名单 tag、或 slug 不在扫描报告里 → 连测试仓都进不来（防乱注入）。</li>
    </ul>
  </div>
  <div class="two" style="margin-top:12px">
    <div class="card">
      <div class="ch">当前 {D['n']} 条按"为什么进测试仓"分</div>
      <table class="grid"><tbody>
        <tr><td class="lbl">太便宜 ≤$0.40（冷门票）</td><td class="num strong">{len(D['cheap'])} 条</td><td class="num dim">{len(D['cheap'])/D['n']*100:.0f}%</td></tr>
        <tr><td class="lbl">太贵 ≥$0.85（近乎确定）</td><td class="num strong">{len(D['exp'])} 条</td><td class="num dim">{len(D['exp'])/D['n']*100:.0f}%</td></tr>
        <tr><td class="lbl">黑名单强制</td><td class="num strong">{len(D['bl'])} 条</td><td class="num dim">0%</td></tr>
      </tbody></table>
      <div class="mini">压倒性是"太便宜"—— 说明规则主要在拦<b>冷门低价票</b>。</div>
    </div>
    <div class="card">
      <div class="ch">构成 · 方向与档位</div>
      <table class="grid"><tbody>
        <tr><td class="lbl">方向</td><td class="num">NO {D['n_no']}</td><td class="num">YES {D['n_yes']}</td></tr>
        <tr><td class="lbl">止损档</td><td class="num">事件 {D['n_ev']}</td><td class="num">收敛 {D['n_co']}</td></tr>
        <tr><td class="lbl">仓位大小</td><td class="num dim" colspan="2">用真仓同款公式算，算不出退 $5；<b class="neg">但不动一分钱</b></td></tr>
      </tbody></table>
      <div class="mini">测试仓用<b>真实盘口价</b>盯、<b>真公式</b>算仓位 —— 所以模拟很逼真，只是全程零成本。</div>
    </div>
  </div>
</section>

<section class="break">
  <h2><span class="n">2</span> 能不能真实进入买卖？<em>（核心问题）</em></h2>
  <div class="two">
    <div class="stat">
      <div class="big neg">不能</div>
      <div class="cap"><b>物理隔离，代码级。</b>测试仓活在自己的数据表里，被一个<b>只会写数据库的"干跑"函数</b>评估。这不是一个能翻的开关 —— 要让它真下单，得<b>写新代码</b>。</div>
    </div>
    <div class="card">
      <div class="ch">三条代码级铁证（已逐行走查）</div>
      <div class="tiers-note" style="border:none;padding:0">
        <ul>
          <li><b>①</b> 评估函数 <code>_evaluate_paper_positions</code> 是干跑：注释白纸黑字"绝不调 executor.sell/buy"，只读行情、只算、只写 <code>paper_positions</code> 表。</li>
          <li><b>②</b> 决策函数 <code>_evaluate_position</code> 是<b>纯函数</b>：只返回"该不该卖"的判断，全函数<b>零</b> executor 调用。真正的 <code>executor.sell</code> 全项目只有 <b>1 处</b>，那处只喂<b>真实持仓</b>，测试仓的行根本不进那条路。</li>
          <li><b>③</b> 全部 <b>8 个</b> <code>/api/paper/*</code> 接口（录入/列表/往期/清空/重评/存q）<b>没有一个</b>碰 executor 或付费 API；/paper 页按钮里也<b>没有</b>"转真买"。</li>
        </ul>
      </div>
    </div>
  </div>
  <div class="mini danger" style="margin-top:12px">
    <b>要特别澄清一个误区 →</b> "测试仓能不能真下单" <b>不等于</b> "能不能把这些漂亮的模拟仓变现"。就算以后加了"一键转真买"，它也是按<b>今天的价</b>买、不是测试仓当初记的价 —— 测试仓的模拟盈亏<b>搬不过来</b>。真正的杠杆是那条 <b>0.40–0.85 分流带</b>：你调它，以后落在新区间的<b>新选品</b>才会真买；已有测试仓只是"规则校准的证据"，不是能搬走的钱。
  </div>
  <div class="mini" style="margin-top:8px">附：测试仓<b>重评免费</b>（只生成 prompt 让你贴 Claude，不调付费 API）；亏损<b>天然封顶</b>（便宜票 + $0.05 地板，单笔最多亏进去那点本金）；<b>不占</b>真金额度。</div>
</section>

<section>
  <h2><span class="n">3</span> 数据分析 · 赢在哪、亏在哪</h2>
  <div class="two" style="margin-bottom:12px">
    <div class="stat"><div class="big pos">{'+' if D['net']>=0 else '−'}${abs(D['net']):.2f}</div>
      <div class="cap">18 仓已了结的<b>模拟净盈亏</b>。赢家合计 <b class="pos">+${D['win_sum']:.2f}</b>，输家合计 <b class="neg">−${abs(D['loss_sum']):.2f}</b>。</div></div>
    <div class="stat"><div class="big">{D['win_rate']:.0f}<span class="s">%</span></div>
      <div class="cap"><b>胜率</b>（{len(D['wins'])} 赢 / {len(D['loss'])} 亏）。平均每赢 <b class="pos">+${D['avg_win']:.2f}</b>，平均每亏 <b class="neg">−${abs(D['avg_loss']):.2f}</b> —— <b>赢的大、亏的小</b>，所以不到四成胜率还能净赚。</div></div>
  </div>
  <div class="callout" style="margin:0 0 14px">
    <div class="co-h" style="font-size:13px">🔑 为什么胜率 39% 还赚钱：不对称</div>
    <p style="margin:0"><b>赢家全是便宜票"翻倍"</b>（+100%~+233%，被"事件型翻倍先到→全卖"或收敛止盈吃到）；<b>输家全是砸到 $0.05 地板或回撤止损</b>（亏损被硬封顶在 ~$1–3）。花小钱买冷门，中了翻几倍、没中亏光那点本 —— 典型彩票式赔付结构。</p>
  </div>
  <h2 style="font-size:12.5px"><span class="n" style="width:18px;height:18px;font-size:10px;background:var(--pos)">✓</span> 赢家 {len(D['wins'])} 仓 · 模拟 <b class="pos">+${D['win_sum']:.2f}</b></h2>
  <table class="grid closed"><thead><tr><th>模拟盈亏$</th><th>方向@入场</th><th>仓位</th><th>档</th><th>卖出方式</th><th>市场</th></tr></thead>
    <tbody>{win_rows(D['wins'])}</tbody></table>
  <h2 style="font-size:12.5px;margin-top:14px"><span class="n" style="width:18px;height:18px;font-size:10px;background:var(--neg)">✕</span> 输家 {len(D['loss'])} 仓 · 模拟 <b class="neg">−${abs(D['loss_sum']):.2f}</b></h2>
  <table class="grid closed"><thead><tr><th>模拟盈亏$</th><th>方向@入场</th><th>仓位</th><th>档</th><th>止损方式</th><th>市场</th></tr></thead>
    <tbody>{loss_rows(D['loss'])}</tbody></table>
  <h2 style="font-size:12.5px;margin-top:14px"><span class="n" style="width:18px;height:18px;font-size:10px;background:var(--dim)">…</span> 仍在跑 {len(D['open'])} 仓 · 还没触发模拟卖点</h2>
  <table class="grid closed"><thead><tr><th>方向@入场</th><th>仓位</th><th>档</th><th>为何进测试仓</th><th>现价</th><th>市场</th></tr></thead>
    <tbody>{open_rows(D['open'])}</tbody></table>
</section>

<section class="break">
  <h2><span class="n">4</span> 反事实 · 分流规则是不是留了钱在桌上？</h2>
  <p style="color:var(--ink2);margin-bottom:11px">这 {D['n']} 条是规则<b>拒买</b>的票。模拟净 <b class="pos">+${D['net']:.2f}</b> 意味着"便宜票桶"（尤其擦边 0.30–0.40）<b>可能</b>被规则留了钱在桌上。但在据此改规则之前，四条硬 caveat 必须看：</p>
  <div class="two">
    <div class="card"><div class="ch neg">⚠️ 别急着放开 —— 四条硬约束</div>
      <div class="tiers-note" style="border:none;padding:0"><ul>
        <li><b>① 样本小、方差大：</b>只有 18 仓了结，且 +${D['net']:.2f} 里一大半来自 <b>4 个大翻倍</b>（+$6.46/+$5.55/+$2.28/+$2.10）—— 是运气还是 edge，样本远不够判。</li>
        <li><b>② 跟历史结论相反：</b>老项目实证是"冷门系统性被高估（favorite-longshot bias），&lt;30¢ 的票大多不兑现"。这里却是便宜票赚钱，<b>矛盾</b>，得更多数据。</li>
        <li><b>③ 模拟不含重评：</b>测试仓省 API 不重评；真仓这些便宜票还会被每日巡检/回撤重评，实际结果可能<b>不一样</b>。</li>
        <li><b>④ 成交价存疑：</b>"翻倍卖点"吃的是 best_bid，便宜票<b>流动性差</b>，真买真卖未必能在那个价成交。</li>
      </ul></div>
    </div>
    <div class="card"><div class="ch">贵票桶（≥$0.85）：证据几乎为零</div>
      <div class="mini" style="margin-top:0">3 条里只 1 条了结（+$0.13 小赢），另 2 条仍在跑（含 1 笔 <b>$15</b> 的 <code>us-reissues-iran-oil</code>）。上行空间小、UMA 结算风险、样本不足 —— <b>没有任何证据支持</b>放开这一档。</div>
      <div class="mini danger" style="margin-top:10px"><b>结论：</b>便宜票桶"看着诱人但证据薄"，贵票桶"证据为零"。数据支持的是<b>继续观察 + 谨慎小实验</b>，不是"赶紧放开真买"。</div>
    </div>
  </div>
</section>

<section>
  <h2><span class="n">5</span> 改进建议 · 以及关于"能否真下单"你还需要知道的</h2>
  <div class="rec todo"><div class="rh">建议 1 · 先观察，别动分流规则（默认）</div>
    <ul><li>让测试仓再攒 <b>20–30 条</b>，看"便宜票桶"是不是<b>稳定</b>正收益，而不是被 4 个翻倍撑起来的假象。现在样本不足以改死规则。</li></ul></div>
  <div class="rec todo"><div class="rh">建议 2 · 若要小步试，只放"擦边便宜" + 极小固定仓</div>
    <ul><li>真要试，只把 real 下限从 0.40 松到 <b>~0.30–0.35</b>（擦边票），而且用<b>极小固定仓位</b>（它们是彩票，别用 Kelly 放大），保留 $0.05 地板封顶。这是可控的 A/B，不是全放开。</li></ul></div>
  <div class="rec todo"><div class="rh">建议 3 · 贵票（≥$0.85）维持进测试仓，别碰</div>
    <ul><li>证据不足 + 上行空间小 + 结算风险。那笔 $15 的贵票就是最好的例子：真买它要押 $15 去赚最多几个点，不划算。</li></ul></div>
  <div class="rec done"><div class="rh">要知道 · "让测试仓能真下单" 到底意味着什么</div>
    <ul>
      <li><b>现在没有这个功能</b>，要新写代码（一个"转真买"接口，或改分流带）。不是翻 flag。</li>
      <li>就算加了"一键转真买"，也是按<b>今天的价</b>买 —— 测试仓那些漂亮的模拟盈亏<b>搬不过来</b>，只是历史校准证据。</li>
      <li>真正该调的是 <b>0.40–0.85 那条带</b>：调它，未来落在新区间的<b>新选品</b>就会真买。这才是"让被拒的票能真下单"的正确做法。</li>
      <li>亏损天然封顶（便宜票 + 地板），单笔真买这类票风险有限；但结算样本还薄（仅约 4 笔真结算），方向对错还判不准。</li>
    </ul></div>
</section>

<footer>
  数据来源：<b>v4.db · paper_positions</b>（{D['n']} 行，{D['first']} ~ {D['last']}）+ 对 <code>monitor.py</code> / <code>auto_trader.py</code> / <code>auto_discovery.py</code> / <code>dashboard.py</code> / <code>db.py</code> 的逐行走查。
  本报告<b>只读</b>：未改动任何仓位、参数或代码。模拟盈亏 = <code>would_sell_pnl_usd</code>（测试仓触发规则卖点时的模拟结果，用真实盘口价 + 真 sizing 公式算，但不动一分钱）。
  <span class="gen">Polymarket AUTO · 测试仓专题研究 · 生成于 {REPORT_DATE}</span>
</footer>

</body></html>"""


CSS = r"""
* { margin:0; padding:0; box-sizing:border-box; }
:root{
  --ink:#141a26; --ink2:#41506b; --dim:#7c89a0; --line:#e5e9f2; --line2:#eef1f7;
  --bg:#f6f8fc; --card:#ffffff;
  --pos:#0e8a5f; --posbg:#e7f6ef; --neg:#d13b3b; --negbg:#fdecec; --zero:#8a94a8;
  --brand:#26356b; --brand2:#3f8bd6;
  --ev:#b7791f; --evbg:#fbf3e2; --hy:#2f6fb0; --hybg:#e8f1fa; --co:#7a4fc0; --cobg:#f0e9fb;
}
html{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }
body{ font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  color:var(--ink); background:var(--bg); font-size:11px; line-height:1.5;
  width:820px; margin:0 auto; padding:0 26px 40px; }
.cover{ padding:26px 0 8px; }
.eyebrow{ font-size:10px; letter-spacing:.18em; color:var(--brand2); font-weight:700; }
.cover h1{ font-size:30px; font-weight:800; letter-spacing:-.5px; color:var(--brand); margin:4px 0 6px; }
.cover .sub{ color:var(--ink2); font-size:11px; }
.cover .sub b{ color:var(--ink); }
.kpis{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-top:16px; }
.kpi{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 13px; box-shadow:0 1px 2px rgba(20,26,38,.04); }
.kl{ font-size:10px; color:var(--dim); font-weight:600; }
.kv{ font-size:20px; font-weight:800; letter-spacing:-.5px; margin:3px 0 5px; color:var(--ink); }
.kv.pos{ color:var(--pos); } .kv.neg{ color:var(--neg); } .kv.zero{ color:var(--ink); }
.chip{ display:inline-block; font-size:9px; font-weight:700; padding:2px 6px; border-radius:20px; }
.chip em{ font-style:normal; opacity:.7; font-weight:600; }
.chip.pos{ background:var(--posbg); color:var(--pos); }
.chip.neg{ background:var(--negbg); color:var(--neg); }
.chip.zero,.chip.cheap{ background:#eef1f7; color:var(--zero); }
.callout{ background:linear-gradient(180deg,#fff, #fbfcff); border:1.5px solid #d9e2f2; border-radius:14px; padding:16px 18px; margin:18px 0; box-shadow:0 2px 10px rgba(38,53,107,.06); }
.co-h{ font-size:15px; font-weight:800; color:var(--brand); margin-bottom:7px; }
.pin{ margin-right:4px; }
.callout p{ color:var(--ink2); margin-bottom:11px; }
.callout b{ color:var(--ink); }
.proof{ border:1.5px dashed #cdd8ee; border-radius:11px; padding:11px 13px; background:#fafcff; }
.pf-t{ font-weight:800; color:var(--brand); font-size:12px; margin-bottom:8px; }
.pf-b{ display:flex; align-items:stretch; gap:10px; }
.pf-col{ flex:1; border-radius:9px; padding:10px 12px; }
.pf-col .h{ font-size:10.5px; font-weight:800; margin-bottom:4px; }
.pf-col .b{ font-size:10px; color:var(--ink2); line-height:1.5; }
.pf-col.old{ background:#fbeeee; } .pf-col.old .h{ color:var(--neg); }
.pf-col.new{ background:#e7f6ef; } .pf-col.new .h{ color:var(--pos); }
.pf-col b{ color:var(--ink); }
.arr{ align-self:center; font-size:20px; color:var(--brand2); font-weight:800; }
section{ margin:20px 0; }
h2{ font-size:15px; font-weight:800; color:var(--ink); margin-bottom:9px; display:flex; align-items:center; gap:9px; }
h2 .n{ display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px; background:var(--brand); color:#fff; border-radius:7px; font-size:12px; font-weight:800; }
h2 em{ font-style:normal; font-size:11px; font-weight:600; color:var(--dim); }
table.grid{ width:100%; border-collapse:collapse; font-size:10px; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
table.grid th{ background:#f3f6fc; color:var(--ink2); font-weight:700; text-align:right; padding:7px 9px; border-bottom:1px solid var(--line); white-space:nowrap; }
table.grid th:first-child, table.grid td:first-child{ text-align:left; }
table.grid td{ padding:6px 9px; border-bottom:1px solid var(--line2); text-align:right; white-space:nowrap; }
table.grid tr:last-child td{ border-bottom:none; }
table.grid tbody tr:nth-child(even){ background:#fafbfe; }
table.closed td{ padding-top:4px; padding-bottom:4px; font-size:9.5px; }
td.lbl{ text-align:left; font-weight:600; color:var(--ink); max-width:230px; overflow:hidden; text-overflow:ellipsis; }
td.num{ font-variant-numeric:tabular-nums; }
td.dim{ color:var(--dim); font-weight:500; } td.strong{ font-weight:800; }
.pos{ color:var(--pos); } .neg{ color:var(--neg); } .zero{ color:var(--zero); } .co{ color:var(--co); }
.badge{ display:inline-block; font-size:8.5px; font-weight:800; padding:1.5px 6px; border-radius:5px; }
.b-ev{ background:var(--evbg); color:var(--ev); } .b-hy{ background:var(--hybg); color:var(--hy); } .b-co{ background:var(--cobg); color:var(--co); }
.tiers-note{ margin-top:0; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:11px 14px; }
.tnh{ font-weight:700; margin-bottom:6px; color:var(--ink); font-size:10.5px; }
.tiers-note ul{ list-style:none; }
.tiers-note li{ font-size:10px; color:var(--ink2); padding:3.5px 0; line-height:1.5; }
.tiers-note b{ color:var(--ink); }
.two{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.card{ background:var(--card); border:1px solid var(--line); border-radius:11px; padding:13px 15px; }
.ch{ font-weight:800; font-size:11px; color:var(--ink); margin-bottom:9px; }
.ch.neg{ color:var(--neg); }
.mini{ font-size:9.5px; color:var(--ink2); margin-top:8px; line-height:1.55; }
.mini b{ color:var(--ink); }
.mini.danger{ background:#fff8f0; border:1px solid #f6e1c8; border-radius:8px; padding:9px 12px; color:#8a5a1a; }
.mini.danger b{ color:#7a3d0a; }
.stat{ background:var(--card); border:1px solid var(--line); border-radius:11px; padding:14px 16px; }
.stat .big{ font-size:34px; font-weight:800; color:var(--brand); letter-spacing:-1px; line-height:1; }
.stat .big.pos{ color:var(--pos); } .stat .big.neg{ color:var(--neg); }
.stat .big .s{ font-size:15px; font-weight:700; color:var(--dim); }
.stat .cap{ font-size:10px; color:var(--ink2); margin-top:8px; line-height:1.55; }
.stat .cap b{ color:var(--ink); }
.rec{ border-radius:11px; padding:12px 16px; margin-bottom:11px; }
.rec.done{ background:#eef8f2; border:1px solid #cfeadd; }
.rec.todo{ background:#f4f7fc; border:1px solid var(--line); }
.rh{ font-weight:800; font-size:11.5px; margin-bottom:6px; }
.rec.done .rh{ color:var(--pos); } .rec.todo .rh{ color:var(--brand); }
.rec ul{ margin-left:16px; }
.rec li{ font-size:10px; color:var(--ink2); padding:3px 0; line-height:1.5; }
.rec b{ color:var(--ink); }
code{ background:#eef1f7; padding:1px 4px; border-radius:3px; color:var(--brand); font-size:9px; }
footer{ margin-top:26px; padding-top:12px; border-top:1px solid var(--line); font-size:9px; color:var(--dim); line-height:1.7; }
footer code{ color:var(--ink2); }
footer b{ color:var(--ink2); }
.gen{ display:block; margin-top:6px; color:#aab3c5; font-weight:600; }
@media print{
  body{ width:auto; background:#fff; padding:0; }
  .kpi,.card,.stat,.callout,table.grid{ box-shadow:none; }
  section.break{ break-before:page; }
  .callout,.card,.stat,.rec,tr,thead,.two{ break-inside:avoid; }
  table.grid{ break-inside:auto; }
  h2{ break-after:avoid; }
}
"""


def main():
    D = collect()
    html = build_html(D)
    out = os.path.join(ROOT, "paper_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML -> {out}")
    print(f"测试仓 {D['n']} | 已了结 {D['n_closed']} (赢{len(D['wins'])}/亏{len(D['loss'])}) | "
          f"仍跑 {len(D['open'])} | 模拟净 {D['net']:+.2f} | 胜率 {D['win_rate']:.0f}%")


if __name__ == "__main__":
    main()
