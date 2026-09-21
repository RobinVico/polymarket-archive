#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polymarket AUTO · 运行诊断报告 生成器 (只读)

读实时 /api/auto/holdings + v4.db (closed_positions / auto_reeval_suggestions)
→ 生成自包含 report.html → 用无头 Chrome 打印成 运行诊断报告-<日期>.pdf

用法:
    .venv/bin/python3 scripts/gen_run_report.py [YYYY-MM-DD]
    # 不给日期则默认从环境取 (调用方传), 缺省 today 占位

只读: 不改任何仓位/参数/数据库。历史上一版 PDF 源丢失 (无生成器), 本脚本即为可复现来源。
"""
import json
import os
import sqlite3
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "v4.db")
HOLDINGS_URL = "http://127.0.0.1:5052/api/auto/holdings"

# 上一版 (2026-07-18) 基线, 用于算"本期变化"delta
PREV = {"date": "2026-07-18", "assets": 100.40, "cash": 48.78, "positions": 20,
        "unrealized": 3.17, "realized": -1.08, "closed": 25}


# ----------------------------------------------------------------------------
# 数据采集
# ----------------------------------------------------------------------------
def fetch_holdings():
    with urllib.request.urlopen(HOLDINGS_URL, timeout=12) as r:
        return json.load(r)


def collect(report_date):
    hold = fetch_holdings()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    slug2title = {}
    for r in con.execute("SELECT DISTINCT slug,title FROM auto_reeval_suggestions WHERE title IS NOT NULL"):
        slug2title.setdefault(r["slug"], r["title"])
    for r in con.execute("SELECT DISTINCT slug,title FROM auto_candidates WHERE title IS NOT NULL"):
        slug2title.setdefault(r["slug"], r["title"])

    closed = []
    for r in con.execute(
        "SELECT market_slug,side,avg_entry_price,exit_price,size,realized_pnl_usd,"
        "exit_reason,stop_loss_tier,entry_at,exit_at FROM closed_positions"
    ):
        d = dict(r)
        d["title"] = slug2title.get(r["market_slug"], "")
        d["ret"] = ((r["exit_price"] - r["avg_entry_price"]) / r["avg_entry_price"]
                    if r["avg_entry_price"] else 0.0)
        d["exit_kind"] = classify_exit(r["exit_reason"])
        closed.append(d)
    closed.sort(key=lambda c: -(c["realized_pnl_usd"] or 0))

    realized_total = sum((c["realized_pnl_usd"] or 0) for c in closed)

    reeval = list(con.execute(
        "SELECT loss_pct,action FROM auto_reeval_suggestions WHERE action IS NOT NULL"))
    con.close()

    # 持仓: 计算价格收益 (API 的 pnl_pct 坏, 自己算)
    holdings = hold["positions"]
    for p in holdings:
        p["ret"] = ((p["cur_price"] - p["avg_price"]) / p["avg_price"]
                    if p["avg_price"] else 0.0)
    holdings.sort(key=lambda p: -p["pnl_dollar"])

    return {
        "date": report_date,
        "account": {k: hold[k] for k in ("assets_total", "cash", "position_count",
                                         "total_value", "total_cost", "total_pnl")},
        "realized_total": realized_total,
        "holdings": holdings,
        "closed": closed,
        "by_tier_closed": tier_agg(closed),
        "exit_kind": exit_kind_agg(closed),
        "reeval": reeval_stats(reeval),
    }


def classify_exit(reason):
    r = (reason or "").upper()
    if "TAKE_PROFIT" in r:
        return "止盈"
    if "STOP_LOSS" in r:
        return "止损"
    if "REEVAL" in r:
        return "重评exit"
    if "FORCE" in r or "手动" in (reason or ""):
        return "手动/强平"
    return "其他"


def tier_agg(closed):
    agg = {}
    for r in closed:
        t = r.get("stop_loss_tier") or "unknown"
        a = agg.setdefault(t, {"n": 0, "pnl": 0.0, "win": 0, "loss": 0})
        a["n"] += 1
        v = r.get("realized_pnl_usd") or 0
        a["pnl"] += v
        a["win" if v > 0 else "loss"] += 1
    return agg


def exit_kind_agg(closed):
    agg = {}
    for c in closed:
        a = agg.setdefault(c["exit_kind"], {"n": 0, "pnl": 0.0})
        a["n"] += 1
        a["pnl"] += c["realized_pnl_usd"] or 0
    return agg


def reeval_stats(rows):
    done = [r for r in rows if r["action"]]
    held_losing = sum(1 for r in done if r["loss_pct"] is not None
                      and r["loss_pct"] < -0.02 and r["action"] != "exit")
    deep = sum(1 for r in done if r["loss_pct"] is not None
               and r["loss_pct"] <= -0.40 and r["action"] != "exit")
    dist = {}
    for r in done:
        dist[r["action"]] = dist.get(r["action"], 0) + 1
    return {"n": len(done), "dist": dist, "held_losing": held_losing, "deep": deep}


# ----------------------------------------------------------------------------
# 标签 (slug -> 短中文名)
# ----------------------------------------------------------------------------
LABELS = [
    ("caatsa", "美国解除对土 CAATSA 制裁"),
    ("us-x-iran-diplomatic", "US×Iran 外交会晤(7/31)"),
    ("us-x-iran-effective-cea", "US×Iran 有效停火(8/14)"),
    ("us-iran-60-day", "US-Iran 60天谈判期延长"),
    ("us-iran-final-nuclear", "US-Iran 核协议(闭环测试)"),
    ("us-announces-end-of-iranian-blockade", "US 宣布结束对伊封锁"),
    ("announce-a-blockade", "US 宣布对伊封锁"),
    ("us-reissues-iran-oil", "US 重启对伊石油制裁"),
    ("iran-announce-withdrawal-from-mou", "Iran 退出 MOU 谈判"),
    ("us-announce-withdrawal-from-mou", "US 宣布退出 MOU 谈判"),
    ("iran-military-action", "Iran 对海湾国军事行动"),
    ("israel-military-action", "Israel 军事行动"),
    ("israel-closes-its-airspace", "Israel 关闭领空"),
    ("israel-x-iran-ceasefire", "Israel×Iran 停火延续"),
    ("saudi-arabian-military", "Saudi 对伊军事行动"),
    ("moscow-air-traffic", "Moscow 航空管制(7/31)"),
    ("russia-enter-vasylivka", "Russia 进入 Vasylivka(7/31)"),
    ("russia-capture-kostyantynivka", "Russia 攻占 Kostyantynivka"),
    ("russia-and-ukraine-hold", "俄乌举行外交会谈"),
    ("google-gemini-pro", "Google Gemini Pro 发布"),
    ("claude-opus", "Claude Opus 模型发布"),
    ("gpt-6", "GPT-6 于 8/21 前发布"),
    ("ornn-h100", "Ornn H100 指数区间"),
    ("bitcoin-hit-1m", "Bitcoin 在 GTA VI 前到 $1M"),
    ("elon-musks-net-worth", "Elon Musk 净资产区间"),
    ("wesley-bell", "Wesley Bell 民主党提名"),
    ("haley-stevens", "Haley Stevens 密歇根提名"),
    ("cori-bush", "Cori Bush 民主党提名"),
    ("mike-lindell", "Mike Lindell 赢 MN 州长"),
    ("trump-be-in-the-wc-champions", "Trump 现身 WC 冠军合影"),
    ("trump-post", "Trump 在 Truth 发「World Cup」"),
    ("trump-declassifies-new-ufo", "Trump 解密新 UFO 文件"),
    ("trump-meet-with-netanyahu", "Trump 会晤 Netanyahu(7/31)"),
    ("donald-trump-publicly-insult", "Trump 公开侮辱某人"),
    ("france-win-the-2026-fifa", "France 夺世界杯(体育误买)"),
    ("at-least-5000-cycl", "5000辆共享单车?(谜市场)"),
    ("untitled-market", "untitled 谜市场(无标题)"),
]


def label(slug, title=""):
    s = (slug or "").lower()
    for key, name in LABELS:
        if key in s:
            return name
    if title:
        return title if len(title) <= 34 else title[:33] + "…"
    return (slug or "?")[:34]


# ----------------------------------------------------------------------------
# HTML 生成
# ----------------------------------------------------------------------------
def money(v, plus=True):
    sign = "+" if (v >= 0 and plus) else ("−" if v < 0 else "")
    return f"{sign}${abs(v):.2f}"


def pct(v):
    return f"{'+' if v >= 0 else '−'}{abs(v)*100:.1f}%"


def cls(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "zero")


def tier_badge(t):
    m = {"event_driven": ("事件", "ev"), "hybrid": ("综合", "hy"),
         "convergent": ("收敛", "co"), "unknown": ("—", "un")}
    name, k = m.get(t, ("—", "un"))
    return f'<span class="badge b-{k}">{name}</span>'


def holding_rows(rows):
    out = []
    for p in rows:
        out.append(
            f'<tr><td class="lbl">{label("", p["title"])}</td>'
            f'<td>{p["side"]}</td>'
            f'<td class="{cls(p["pnl_dollar"])} num">{money(p["pnl_dollar"])}</td>'
            f'<td class="{cls(p["ret"])} num">{pct(p["ret"])}</td>'
            f'<td class="num dim">{p["avg_price"]:.3f}→{p["cur_price"]:.3f}</td>'
            f'<td class="num dim">{p["q"]:.2f}</td>'
            f'<td>{tier_badge(p["stop_loss_tier"])}</td>'
            f'<td class="st">{p["monitor_state"]}</td></tr>'
        )
    return "\n".join(out)


def closed_rows(rows):
    out = []
    for c in rows:
        v = c["realized_pnl_usd"] or 0
        out.append(
            f'<tr><td class="{cls(v)} num strong">{money(v)}</td>'
            f'<td>{c["side"]}</td>'
            f'<td class="num dim">{c["avg_entry_price"]:.3f}→{c["exit_price"]:.3f}</td>'
            f'<td class="{cls(c["ret"])} num">{pct(c["ret"])}</td>'
            f'<td>{tier_badge(c["stop_loss_tier"])}</td>'
            f'<td class="ek ek-{c["exit_kind"]}">{c["exit_kind"]}</td>'
            f'<td class="lbl">{label(c["market_slug"], c["title"])}</td></tr>'
        )
    return "\n".join(out)


def tier_bar(agg):
    """收敛/综合/事件 已平仓已实现盈亏 横条 (0 居中)."""
    order = ["event_driven", "hybrid", "convergent"]
    names = {"event_driven": "事件型", "hybrid": "综合型", "convergent": "收敛型"}
    vals = [(names[t], agg.get(t, {"pnl": 0, "n": 0, "win": 0, "loss": 0})) for t in order]
    mx = max(1.0, max(abs(a["pnl"]) for _, a in vals))
    rows = []
    for name, a in vals:
        w = abs(a["pnl"]) / mx * 46
        side = "r" if a["pnl"] >= 0 else "l"
        bar = (f'<span class="tbar {"pos" if a["pnl"] >= 0 else "neg"} {side}" '
               f'style="width:{w}%"></span>')
        rows.append(
            f'<div class="tier-row"><span class="tn">{name}</span>'
            f'<span class="tmid">{bar}</span>'
            f'<span class="tv {cls(a["pnl"])}">{money(a["pnl"])}</span>'
            f'<span class="tc">{a["n"]}笔 · 赢{a["win"]}/亏{a["loss"]}</span></div>'
        )
    return "\n".join(rows)


def build_html(D):
    acc, R = D["account"], D["realized_total"]
    dA = acc["assets_total"] - PREV["assets"]
    dC = acc["cash"] - PREV["cash"]
    dP = acc["position_count"] - PREV["positions"]
    dU = acc["total_pnl"] - PREV["unrealized"]
    dR = R - PREV["realized"]
    n_closed = len(D["closed"])
    win = [c for c in D["closed"] if (c["realized_pnl_usd"] or 0) > 0]
    loss = [c for c in D["closed"] if (c["realized_pnl_usd"] or 0) < 0]
    win_sum = sum(c["realized_pnl_usd"] for c in win)
    loss_sum = sum(c["realized_pnl_usd"] for c in loss)
    ek = D["exit_kind"]
    tc = D["by_tier_closed"]
    rv = D["reeval"]
    hold_win = [p for p in D["holdings"] if p["pnl_dollar"] > 0]
    hold_loss = [p for p in D["holdings"] if p["pnl_dollar"] <= 0]

    def delta_chip(v, unit="$", asint=False, neutral=False):
        c = "zero" if neutral else ("pos" if v > 0 else ("neg" if v < 0 else "zero"))
        if asint:
            s = f"{'+' if v > 0 else ''}{int(v)}"
        else:
            s = f"{'+' if v >= 0 else '−'}{unit}{abs(v):.2f}" if unit == "$" else f"{'+' if v >= 0 else '−'}{abs(v):.2f}{unit}"
        return f'<span class="chip {c}">{s} <em>vs {PREV["date"][5:]}</em></span>'

    # 值颜色: 只有两个 P&L 指标按盈亏上色; 总资产/现金/持仓 中性 (绿色会误读成"盈利")
    # delta chip: 现金/持仓变化本身无好坏 (现金降=拿去开仓), 标中性灰; 总资产/P&L 按方向上色
    kpis = [
        ("总资产", f"${acc['assets_total']:.2f}", delta_chip(dA), ""),
        ("现金", f"${acc['cash']:.2f}", delta_chip(dC, neutral=True), ""),
        ("当前持仓", f"{acc['position_count']} 仓", delta_chip(dP, asint=True, neutral=True), ""),
        ("浮动盈亏", money(acc["total_pnl"]), delta_chip(dU), cls(acc["total_pnl"])),
        ("已实现累计", money(R), delta_chip(dR), cls(R)),
    ]
    kpi_html = "\n".join(
        f'<div class="kpi"><div class="kl">{l}</div><div class="kv {c}">{v}</div>'
        f'<div class="kd">{d}</div></div>'
        for l, v, d, c in kpis
    )

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>report.html</title>
<style>{CSS}</style></head><body>

<header class="cover">
  <div class="ct">
    <div class="eyebrow">POLYMARKET · 全自动账户 (真金 sig=3)</div>
    <h1>运行诊断报告</h1>
    <div class="sub">数据区间 <b>2026-07-08 ~ 07-20</b>（约 12 天） · 生成于 <b>{D['date']}</b> · 版本 <b>v8.3.1</b> · 本报告只读，未改动任何仓位/参数</div>
  </div>
  <div class="kpis">{kpi_html}</div>
</header>

<section class="callout">
  <div class="co-h"><span class="pin">📌</span> 本期头条：上一版报告点名的病，这两天全动了手术</div>
  <p>07-18 那版报告的结论是一句话：<b>「事件型止损名存实亡，深亏拖着不卖，是账户最大亏损来源」</b>，并点名下一个雷是 Claude Opus。
  这两天（v8.1.0 → v8.3.1）把它建议的几乎全做了 —— 而且 <b class="pos">Claude Opus 第一笔实战就被新止损救下</b>。</p>
  <table class="ba">
    <thead><tr><th>上版诊断的病</th><th>以前的做法</th><th>现在的新策略（版本）</th></tr></thead>
    <tbody>
      <tr><td>事件型深亏拖着不卖<span class="tag">最大亏损源</span></td>
          <td>砸穿 −60% 只交重评；重评想卖又被护栏降级 → 一路烂到 $0.05 地板</td>
          <td class="fx"><b>−50% 直接硬平仓</b>（8.1.0），谁都越不过；<b>删 exit 护栏</b>（8.1.0）重评说卖立刻卖</td></tr>
      <tr><td>收敛型砸穿也交重评、拖</td>
          <td>砸穿 → PENDING_REEVAL 等重评</td>
          <td class="fx"><b>直接平仓、不重评</b>（8.3.0）</td></tr>
      <tr><td>重评能「关掉止损继续扛」</td>
          <td>cancel_autostop 决策选项</td>
          <td class="fx"><b>删掉</b>（8.3.0），重评不能再关止损</td></tr>
      <tr><td>盘中触发重评太迟钝</td>
          <td>需 −30% + 6h 冷却才触发</td>
          <td class="fx">任何盈亏水平、<b>从最好点回撤 5pp 即触发</b>（8.3.0）</td></tr>
      <tr><td>GLM 跟市场分歧被打五折、太怂</td>
          <td>prompt 里 ×0.5</td>
          <td class="fx">挪到 Python <b>信自己八成 ×0.8</b>（8.2.0）edge 更大、更敢下</td></tr>
    </tbody>
  </table>
  <div class="proof">
    <div class="pf-t">🎯 铁证：Claude Opus（上版预言的「下一个 Gemini」）</div>
    <div class="pf-b">
      <div class="pf-col old"><div class="h">旧规则会怎样</div><div class="b">事件型<b>没有硬止损</b>，只会 −60% 交重评、重评又被护栏拦住 → 复刻 Gemini 一路烂到 <b class="neg">−76%</b></div></div>
      <div class="arr">→</div>
      <div class="pf-col new"><div class="h">新规则实际发生</div><div class="b">07-18 早 <b>−50% 硬止损直接触发</b>，砍在 0.46→0.22（<b class="neg">−52%</b>，亏 <b>−$0.72</b>）就收手，没让它继续烂</div></div>
    </div>
  </div>
</section>

<section>
  <h2><span class="n">1</span> 当前持仓 · 赚钱的仓 <em>（{len(hold_win)} 仓，浮盈 {money(sum(p['pnl_dollar'] for p in hold_win))}）</em></h2>
  <table class="grid">
    <thead><tr><th>市场</th><th>方向</th><th>盈亏$</th><th>价格收益</th><th>入场→现价</th><th>q</th><th>止损档</th><th>状态</th></tr></thead>
    <tbody>{holding_rows(hold_win)}</tbody>
  </table>
</section>

<section>
  <h2><span class="n">2</span> 当前持仓 · 亏钱的仓 <em>（{len(hold_loss)} 仓，浮亏 {money(sum(p['pnl_dollar'] for p in hold_loss))}）</em></h2>
  <table class="grid">
    <thead><tr><th>市场</th><th>方向</th><th>盈亏$</th><th>价格收益</th><th>入场→现价</th><th>q</th><th>止损档</th><th>状态</th></tr></thead>
    <tbody>{holding_rows(hold_loss)}</tbody>
  </table>
  <div class="tiers-note">
    <div class="tnh">三档止损类型现在各是什么行为（已按新策略更新）：</div>
    <ul>
      <li>{tier_badge('event_driven')} <b>事件型</b>（政治/外交/模型发布，占 18/25 仓）— 跌破成本 <b>−50% 直接硬平仓</b>（新增，越不过）；盘中从最好点回撤 5pp 触发一次重评；$0.05 地板保留。</li>
      <li>{tier_badge('hybrid')} <b>综合型</b> — 从最高价回撤 <b>35% 直接平仓</b>（不交重评）。</li>
      <li>{tier_badge('convergent')} <b>收敛型</b> — 从最高价回撤 <b>20%（≤3天 12%）直接平仓</b>（新：原来交重评，现改直接平）。</li>
    </ul>
  </div>
</section>

<section class="break">
  <h2><span class="n">3</span> 全部已平仓盈亏表 <em>（{n_closed} 笔，按盈亏从大到小；<b class="hl">新增「止损档」列</b>）</em></h2>
  <table class="grid closed">
    <thead><tr><th>盈亏$</th><th>方向</th><th>入场→卖出</th><th>收益率</th><th>止损档</th><th>平仓方式</th><th>市场</th></tr></thead>
    <tbody>{closed_rows(D['closed'])}</tbody>
  </table>
  <div class="sumline">
    合计 <b class="{cls(R)}">{money(R)}</b> ｜ 赢 {len(win)} 笔 <b class="pos">{money(win_sum)}</b> ｜ 亏 {len(loss)} 笔 <b class="neg">{money(loss_sum)}</b>{f' ｜ 打平 {n_closed-len(win)-len(loss)} 笔' if (n_closed-len(win)-len(loss)) else ''}
  </div>
</section>

<section>
  <h2><span class="n">4</span> 钱亏在哪</h2>
  <div class="two">
    <div class="card">
      <div class="ch">按止损档看：亏损方已经换人了</div>
      {tier_bar(tc)}
      <p class="mini">上一版里 <b>事件型是最大亏损源</b>；新止损上线后事件型靠几个大止盈翻成 <b class="pos">{money(tc.get('event_driven',{}).get('pnl',0))}</b>，
      亏损主力变成 <b class="neg">综合型 {money(tc.get('hybrid',{}).get('pnl',0))}</b> 和 <b class="neg">收敛型 {money(tc.get('convergent',{}).get('pnl',0))}</b>。</p>
    </div>
    <div class="card">
      <div class="ch">按平仓方式看：亏几乎全来自「止损」这 {ek.get('止损',{}).get('n',0)} 笔</div>
      <div class="ekbars">
        {"".join(f'<div class="ekrow"><span class="ekn">{k}</span><span class="ekc {cls(a["pnl"])}">{money(a["pnl"])}</span><span class="ekq">{a["n"]}笔</span></div>' for k,a in sorted(ek.items(), key=lambda x:-x[1]["pnl"]))}
      </div>
      <p class="mini">赢的钱全靠 <b class="pos">止盈（{money(ek.get('止盈',{}).get('pnl',0))}）</b>，
      亏的钱全在 <b class="neg">止损（{money(ek.get('止损',{}).get('pnl',0))}）</b> 和 <b class="neg">浅水重评 exit（{money(ek.get('重评exit',{}).get('pnl',0))}）</b>。典型「砍赢容易、砍输狠」。</p>
    </div>
  </div>
  <div class="worst">
    <div class="ch">亏得最狠的几笔（前 4 笔都是老账 / fix 前的事件型无止损产物）：</div>
    <table class="grid mini-t">
      <thead><tr><th>亏$</th><th>入场→卖出</th><th>跌了多少才卖</th><th>止损档</th><th>市场</th><th>性质</th></tr></thead>
      <tbody>
        <tr><td class="neg num strong">−$2.60</td><td class="num dim">0.682→0.162</td><td class="neg num">−76%</td><td>{tier_badge('event_driven')}</td><td class="lbl">Google Gemini（YES 那半）</td><td class="why">fix 前：被护栏挡着扛 6 次才放行</td></tr>
        <tr><td class="neg num strong">−$1.99</td><td class="num dim">0.710→0.045</td><td class="neg num">−94%</td><td>{tier_badge('event_driven')}</td><td class="lbl">US 宣布对伊封锁</td><td class="why">fix 前：一路扛到 $0.05 地板</td></tr>
        <tr><td class="neg num strong">−$1.17</td><td class="num dim">0.756→0.522</td><td class="neg num">−31%</td><td>{tier_badge('hybrid')}</td><td class="lbl">untitled 谜市场</td><td class="why">hybrid 砸穿平（相对及时）</td></tr>
        <tr><td class="neg num strong">−$0.85</td><td class="num dim">0.601→0.516</td><td class="neg num">−14%</td><td>{tier_badge('convergent')}</td><td class="lbl">Elon Musk 净资产区间</td><td class="why">07-20 新：收敛型回撤直接平（本是浮盈仓，回落被砍）</td></tr>
        <tr><td class="neg num strong">−$0.72</td><td class="num dim">0.460→0.220</td><td class="neg num">−52%</td><td>{tier_badge('event_driven')}</td><td class="lbl">Claude Opus 模型发布</td><td class="why"><b>新 −50% 硬止损砍住</b>（否则就是下一个 Gemini）</td></tr>
      </tbody>
    </table>
  </div>
  <p class="mini danger">⚠️ 老问题没解决：3 个 <b>「untitled 谜市场」（无标题）</b>合计仍贡献约 <b class="neg">−$2.17</b> 亏损；标题都抓不到，很可能根本不该进宇宙，值得单独查。</p>
</section>

<section class="break">
  <h2><span class="n">5</span> 钱赚在哪 · 最大的几笔</h2>
  <table class="grid">
    <thead><tr><th>赚$</th><th>方向</th><th>入场→卖出</th><th>收益率</th><th>止损档</th><th>平仓方式</th><th>市场</th></tr></thead>
    <tbody>{closed_rows(win[:8])}</tbody>
  </table>
  <p class="mini">最大的几笔<b>全部来自事件型的止盈</b>（翻倍全卖 / 0.92 卖一半 + 后半保护）。
  最讽刺也最有信息量的是 <b>Google Gemini</b>：同一个市场，<b class="pos">NO 那两半各赚 +$2.22（买 0.49 卖 0.94，方向押对赢麻了）</b>，
  可 GLM 后来又<b class="neg">反手押 YES，亏回 −$2.60</b> —— 净 +$1.84。赢在方向对的半边，输在它自己又跳到反方向。</p>
</section>

<section>
  <h2><span class="n">6</span> GLM 深水扛单复盘</h2>
  <div class="two">
    <div class="stat">
      <div class="big">{rv['dist'].get('exit',0)} <span class="s">/ {rv['n']}</span></div>
      <div class="cap">{rv['n']} 次重评决策里，只有 {rv['dist'].get('exit',0)} 次主动选 <b>exit</b>（{rv['dist'].get('exit',0)*100//max(rv['n'],1)}%）；其余全是 update_q（{rv['dist'].get('update_q',0)}）/ hold（{rv['dist'].get('hold',0)}）。</div>
    </div>
    <div class="stat">
      <div class="big neg">{rv['deep']} <span class="s">次</span></div>
      <div class="cap">已经亏 <b>&gt;40%</b> 了还选择继续扛的决策有 {rv['deep']} 次（下跌中扛单共 {rv['held_losing']} 次）。GLM 几乎从不自己认输。</div>
    </div>
  </div>
  <p class="mini">结论没变、而且更硬了：<b>不能指望重评自己割肉</b> —— 它算出来的「合理价」总高于现价，深水里一直赌反弹。
  所以 <b>硬止损（−50% / 收敛&综合回撤直接平）才是真正兜底的那道闸</b>，这也正是这两天补上的东西。Claude Opus 就是活证据：靠的是硬止损，不是重评。</p>
</section>

<section class="break">
  <h2><span class="n">7</span> 还有什么可以改（按性价比）</h2>
  <div class="rec done">
    <div class="rh">✅ 上一版建议、这两天已经做了</div>
    <ul>
      <li>事件型加真正的硬止损 → <b>−50% 直接平仓</b>（8.1.0）</li>
      <li>删/绕过重评 exit 护栏 → <b>护栏整个删掉</b>（8.1.0）</li>
      <li>收敛型砸穿别再拖 → <b>直接平仓</b>（8.3.0）</li>
      <li>重评不该能关止损 → <b>删 cancel_autostop</b>（8.3.0）</li>
    </ul>
  </div>
  <div class="rec todo">
    <div class="rh">⬜ 还没做、建议排期</div>
    <ul>
      <li><b>补账户级总回撤闸</b>：07-18 删了月度 DD 预算后留了真空，现在账户级总敞口没有任何总闸。建议「未实现总回撤 &gt; $N 就停开新仓 / 报警」。</li>
      <li><b>查那 3 个 untitled 谜市场</b>：无标题、合计贡献约 −$2.17，很可能根本不该进宇宙。</li>
      <li><b>止盈/止损对称化</b>：现在止盈只卖一半、止损全卖，放大「砍赢封顶、砍输放任」。可考虑止盈也留、或止损也分批。</li>
      <li><b>浅水频繁小额进出</b>：{ek.get('重评exit',{}).get('n',0)} 笔重评 exit 合计 {money(ek.get('重评exit',{}).get('pnl',0))}，大半是 ±$0.05 的小进小出，产出接近 0 却每次烧 API + 价差。</li>
    </ul>
  </div>
</section>

<footer>
  数据源：运行中的 <code>/api/auto/holdings</code>（实时现金/持仓/浮盈）+ <code>v4.db</code>（closed_positions / auto_reeval_suggestions）。
  收益率 = (卖出/现价 − 入场) / 入场；已实现 = closed_positions 累计。深水扛单统计 = 逐条重评决策的 loss_pct × action。
  代码路径：monitor.py 三档止损与 −50% 硬止损（EVENT_DRIVEN_HARD_STOP_PCT）、auto_reeval.py 重评决策。<b>本报告只读，未触碰任何仓位或参数。</b>
  <span class="gen">Polymarket AUTO v8.3.1 · 生成于 {D['date']}</span>
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

/* cover */
.cover{ padding:26px 0 8px; }
.eyebrow{ font-size:10px; letter-spacing:.18em; color:var(--brand2); font-weight:700; }
.cover h1{ font-size:30px; font-weight:800; letter-spacing:-.5px; color:var(--brand);
  margin:4px 0 6px; }
.cover .sub{ color:var(--ink2); font-size:11px; }
.cover .sub b{ color:var(--ink); }
.kpis{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-top:16px; }
.kpi{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 13px;
  box-shadow:0 1px 2px rgba(20,26,38,.04); }
.kl{ font-size:10px; color:var(--dim); font-weight:600; }
.kv{ font-size:20px; font-weight:800; letter-spacing:-.5px; margin:3px 0 5px; color:var(--ink); }
.kv.pos{ color:var(--pos); } .kv.neg{ color:var(--neg); } .kv.zero{ color:var(--ink); }
.chip{ display:inline-block; font-size:9px; font-weight:700; padding:2px 6px; border-radius:20px; }
.chip em{ font-style:normal; opacity:.6; font-weight:600; }
.chip.pos{ background:var(--posbg); color:var(--pos); }
.chip.neg{ background:var(--negbg); color:var(--neg); }
.chip.zero{ background:#eef1f7; color:var(--zero); }

/* callout */
.callout{ background:linear-gradient(180deg,#fff, #fbfcff); border:1.5px solid #d9e2f2;
  border-radius:14px; padding:16px 18px; margin:18px 0; box-shadow:0 2px 10px rgba(38,53,107,.06); }
.co-h{ font-size:15px; font-weight:800; color:var(--brand); margin-bottom:7px; }
.pin{ margin-right:4px; }
.callout p{ color:var(--ink2); margin-bottom:11px; }
.callout b{ color:var(--ink); }
.ba{ width:100%; border-collapse:collapse; font-size:10px; margin-bottom:12px; }
.ba th{ background:#eef2fa; color:var(--ink2); text-align:left; padding:6px 8px; font-weight:700;
  border:1px solid var(--line); }
.ba td{ padding:6px 8px; border:1px solid var(--line); vertical-align:top; }
.ba td.fx{ background:#f0f9f3; }
.ba td.fx b{ color:var(--pos); }
.tag{ display:inline-block; background:var(--negbg); color:var(--neg); font-size:8px; font-weight:800;
  padding:1px 5px; border-radius:4px; margin-left:5px; vertical-align:middle; }
.proof{ border:1.5px dashed #cdd8ee; border-radius:11px; padding:11px 13px; background:#fafcff; }
.pf-t{ font-weight:800; color:var(--brand); font-size:12px; margin-bottom:8px; }
.pf-b{ display:flex; align-items:stretch; gap:10px; }
.pf-col{ flex:1; border-radius:9px; padding:9px 11px; }
.pf-col .h{ font-size:10px; font-weight:800; margin-bottom:3px; }
.pf-col .b{ font-size:10px; color:var(--ink2); }
.pf-col.old{ background:#fbeeee; } .pf-col.old .h{ color:var(--neg); }
.pf-col.new{ background:#e7f6ef; } .pf-col.new .h{ color:var(--pos); }
.pf-col b{ color:var(--ink); }
.arr{ align-self:center; font-size:20px; color:var(--brand2); font-weight:800; }

/* sections */
section{ margin:20px 0; }
h2{ font-size:15px; font-weight:800; color:var(--ink); margin-bottom:9px;
  display:flex; align-items:center; gap:9px; }
h2 .n{ display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px;
  background:var(--brand); color:#fff; border-radius:7px; font-size:12px; font-weight:800; }
h2 em{ font-style:normal; font-size:11px; font-weight:600; color:var(--dim); }
h2 em b{ color:var(--ink2); } .hl{ color:var(--brand2)!important; }

/* tables */
table.grid{ width:100%; border-collapse:collapse; font-size:10px; background:var(--card);
  border:1px solid var(--line); border-radius:10px; overflow:hidden; }
table.grid th{ background:#f3f6fc; color:var(--ink2); font-weight:700; text-align:right;
  padding:7px 9px; border-bottom:1px solid var(--line); white-space:nowrap; }
table.grid th:first-child, table.grid td:first-child{ text-align:left; }
table.grid td{ padding:6px 9px; border-bottom:1px solid var(--line2); text-align:right; white-space:nowrap; }
table.grid tr:last-child td{ border-bottom:none; }
table.grid tbody tr:nth-child(even){ background:#fafbfe; }
table.closed td{ padding-top:3.8px; padding-bottom:3.8px; font-size:9.5px; }
table.closed th{ padding-top:5px; padding-bottom:5px; }
td.lbl{ text-align:left; font-weight:600; color:var(--ink); max-width:210px; overflow:hidden;
  text-overflow:ellipsis; }
td.num{ font-variant-numeric:tabular-nums; font-feature-settings:"tnum"; }
td.dim{ color:var(--dim); } td.strong{ font-weight:800; }
td.st,.st{ font-size:8.5px; color:var(--dim); font-weight:700; letter-spacing:.02em; text-align:right; }
.pos{ color:var(--pos); } .neg{ color:var(--neg); } .zero{ color:var(--zero); }
.ek{ font-weight:700; text-align:center!important; font-size:9px; }
.ek-止盈{ color:var(--pos); } .ek-止损{ color:var(--neg); }
.ek-重评exit{ color:var(--hy); } .ek-手动\/强平{ color:var(--dim); }

/* badges */
.badge{ display:inline-block; font-size:8.5px; font-weight:800; padding:1.5px 6px; border-radius:5px; }
.b-ev{ background:var(--evbg); color:var(--ev); } .b-hy{ background:var(--hybg); color:var(--hy); }
.b-co{ background:var(--cobg); color:var(--co); } .b-un{ background:#eef1f7; color:var(--dim); }

.sumline{ text-align:right; font-size:11px; color:var(--ink2); margin-top:7px; padding-right:4px; }
.sumline b{ font-weight:800; }

/* tier note */
.tiers-note{ margin-top:11px; background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:11px 14px; }
.tnh{ font-weight:700; margin-bottom:6px; color:var(--ink); font-size:10.5px; }
.tiers-note ul{ list-style:none; }
.tiers-note li{ font-size:10px; color:var(--ink2); padding:3px 0; }
.tiers-note b{ color:var(--ink); }

/* two-col cards */
.two{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.card{ background:var(--card); border:1px solid var(--line); border-radius:11px; padding:13px 15px; }
.ch{ font-weight:800; font-size:11px; color:var(--ink); margin-bottom:9px; }
.mini{ font-size:9.5px; color:var(--ink2); margin-top:8px; line-height:1.55; }
.mini b{ color:var(--ink); }
.mini.danger{ background:#fff8f0; border:1px solid #f6e1c8; border-radius:8px; padding:8px 11px; color:#8a5a1a; }
.mini.danger b{ color:#7a3d0a; }

/* tier bars */
.tier-row{ display:grid; grid-template-columns:52px 1fr 58px 92px; align-items:center; gap:8px;
  padding:5px 0; font-size:10px; }
.tn{ font-weight:700; color:var(--ink); }
.tmid{ position:relative; height:14px; background:linear-gradient(90deg,transparent 49.6%,#d7deec 49.6%,#d7deec 50.4%,transparent 50.4%); border-radius:3px; }
.tbar{ position:absolute; top:2px; height:10px; border-radius:3px; }
.tbar.pos{ left:50%; background:var(--pos); } .tbar.neg{ right:50%; background:var(--neg); }
.tv{ text-align:right; font-weight:800; font-variant-numeric:tabular-nums; }
.tc{ text-align:right; color:var(--dim); font-size:9px; }

/* exit-kind bars */
.ekbars{ display:flex; flex-direction:column; gap:5px; }
.ekrow{ display:grid; grid-template-columns:1fr 62px 42px; align-items:center; font-size:10px; }
.ekn{ font-weight:700; color:var(--ink); }
.ekc{ text-align:right; font-weight:800; font-variant-numeric:tabular-nums; }
.ekq{ text-align:right; color:var(--dim); font-size:9px; }

.worst{ margin-top:12px; }
.mini-t{ font-size:9.5px; }
.mini-t td.why,.why{ text-align:left; font-size:9px; color:var(--ink2); }
.mini-t th:last-child{ text-align:left; }

/* stat blocks */
.stat{ background:var(--card); border:1px solid var(--line); border-radius:11px; padding:14px 16px; }
.stat .big{ font-size:30px; font-weight:800; color:var(--brand); letter-spacing:-1px; }
.stat .big.neg{ color:var(--neg); }
.stat .big .s{ font-size:14px; font-weight:700; color:var(--dim); }
.stat .cap{ font-size:10px; color:var(--ink2); margin-top:5px; }
.stat .cap b{ color:var(--ink); }

/* recommendations */
.rec{ border-radius:11px; padding:12px 16px; margin-bottom:11px; }
.rec.done{ background:#eef8f2; border:1px solid #cfeadd; }
.rec.todo{ background:#f4f7fc; border:1px solid var(--line); }
.rh{ font-weight:800; font-size:11.5px; margin-bottom:6px; }
.rec.done .rh{ color:var(--pos); } .rec.todo .rh{ color:var(--brand); }
.rec ul{ margin-left:16px; }
.rec li{ font-size:10px; color:var(--ink2); padding:2.5px 0; }
.rec b{ color:var(--ink); }

footer{ margin-top:26px; padding-top:12px; border-top:1px solid var(--line); font-size:9px;
  color:var(--dim); line-height:1.6; }
footer code{ background:#eef1f7; padding:1px 4px; border-radius:3px; color:var(--ink2); font-size:8.5px; }
footer b{ color:var(--ink2); }
.gen{ display:block; margin-top:6px; color:#aab3c5; font-weight:600; }

@page{ size:A4; margin:12mm 10mm; }
@media print{
  body{ width:auto; background:#fff; padding:0; }
  .kpi,.card,.stat,.callout,table.grid{ box-shadow:none; }
  section.break{ break-before:page; }
  .callout,.card,.stat,.worst,.rec,.tier-row,tr,thead{ break-inside:avoid; }
  table.grid{ break-inside:auto; }
  h2{ break-after:avoid; }
}
"""


def main():
    report_date = sys.argv[1] if len(sys.argv) > 1 else "2026-07-20"
    D = collect(report_date)
    html = build_html(D)
    out_html = os.path.join(ROOT, "report.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    acc = D["account"]
    print(f"HTML -> {out_html}")
    print(f"账户: 总资产 ${acc['assets_total']:.2f} | 现金 ${acc['cash']:.2f} | "
          f"{acc['position_count']}仓 | 浮盈 {money(acc['total_pnl'])} | 已实现 {money(D['realized_total'])}")
    print(f"平仓 {len(D['closed'])} 笔 | 事件{D['by_tier_closed'].get('event_driven',{}).get('pnl',0):+.2f} "
          f"综合{D['by_tier_closed'].get('hybrid',{}).get('pnl',0):+.2f} "
          f"收敛{D['by_tier_closed'].get('convergent',{}).get('pnl',0):+.2f}")


if __name__ == "__main__":
    main()
