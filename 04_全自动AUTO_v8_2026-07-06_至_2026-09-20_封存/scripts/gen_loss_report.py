#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polymarket AUTO · 大亏损复盘专项报告 生成器 (只读)

聚焦 2026-07-20 峰值 $106 → 07-23 $93 这轮 ~$13 回撤:
逐笔割肉/止盈全字段明细 (仓位标签/入场价/股数/平仓方式/事件原因) + 亏损拆解 + 改进策略。

读实时 /api/auto/holdings + v4.db (closed_positions / portfolio_snapshot)
→ report_loss.html → 无头 Chrome 打印 亏损复盘报告-<日期>.pdf

复用 gen_run_report 的 CSS/格式化助手, 保持两份报告同一套设计语言。
"""
import datetime
import os
import sqlite3
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_run_report import CSS, money, pct, cls, tier_badge, label, classify_exit  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "v4.db")
SINCE = "2026-07-20T14:00"   # 峰值之后
PEAK = 105.97               # 07-20 snapshot 峰值 (assets_total)

# 逐笔"事件原因"注解 (slug 子串 → 为什么这么走). 只读数据推不出因果, 人工标注。
WHY = {
    "trump-meet-with-benjamin-neta": "押「7月底前不会见 Netanyahu」→ 会见预期骤升，NO 被打穿",
    "warsh-say-oil": "押「Warsh 记者会会提『油价』」YES → 没提，YES 崩",
    "exactly-0-earthquake": "地震次数区间押反（这类量化冷门 GLM 没边际）",
    "russia-enter-vasylivka": "押「俄军7月底前进不了 Vasylivka」→ 俄军推进，NO 崩",
    "gpt-6": "押「GPT-6 于 8/21 前不发布」→ 发布预期升温，NO 走弱",
    "8-or-fewer-earthquake": "地震次数区间，回撤触发离场（同上冷门）",
    "warsh-say-task-force": "押「Warsh 不会说满20次 task force」→ 押反",
    "untitled-market": "谜市场（无标题）—— 反复贡献亏损，八成不该进宇宙",
    "mike-lindell": "押「Lindell 赢 MN 州长」YES → 概率下滑",
    "usd-be-at-least-1pt9m": "伊朗里亚尔汇率区间押反",
    "us-x-iran-effective-cea": "停火 NO 小幅回撤离场（小亏）",
    "houthis": "押「胡塞不会得手」→ 小幅走反（小亏）",
    # 止盈侧（对冲了一半亏损）
    "trump-post-world-cup": "Trump 真在 Truth 发了「World Cup」→ 方向全中，本轮最大赢",
    "haley-stevens": "提名行情利好持有方向",
    "caatsa": "解除制裁方向押对",
    "us-x-iran-diplomatic": "外交会晤方向押对",
    "trump-be-in-the-wc-champions": "Trump 现身冠军合影 → 兑现到 ~1.0",
    "claude-opus": "方向押对，止盈落袋",
    "donald-trump-publicly-insult": "方向押对，分批止盈",
    "iran-announce-withdrawal": "止盈卖半",
    "russia-capture-kostyantyn": "止盈卖半",
    "ornn-h100": "基本走平",
}


def why(slug):
    s = (slug or "").lower()
    for k, v in WHY.items():
        if k in s:
            return v
    return ""


# 本轮涉及市场的干净中文标签 (补 gen_run_report.LABELS 没覆盖的冷门盘)
LOSS_LABELS = [
    ("trump-meet-with-benjamin", "Trump 会晤 Netanyahu(7/31)"),
    ("warsh-say-oil", "Warsh 记者会提「油价」"),
    ("exactly-0-earthquake", "7月正好 0 次地震"),
    ("russia-enter-vasylivka", "俄军进 Vasylivka(7/31)"),
    ("8-or-fewer-earthquake", "7月地震 ≤8 次"),
    ("warsh-say-task-force", "Warsh 说满20次 task force"),
    ("usd-be-at-least-1pt9m", "里亚尔汇率 ≥1.9M"),
    ("houthis", "胡塞袭船得手"),
    ("trump-post-world-cup", "Trump 发「World Cup」"),
    ("mexico-gdp", "墨西哥 Q2 GDP 区间"),
    ("bank-of-korea", "韩国央行 8月按兵不动"),
]


def llabel(slug, title=""):
    s = (slug or "").lower()
    for k, v in LOSS_LABELS:
        if k in s:
            return v
    return label(slug, title)   # 回退到 gen_run_report 的通用标签映射


def fetch_holdings():
    with urllib.request.urlopen("http://127.0.0.1:5052/api/auto/holdings", timeout=12) as r:
        import json
        return json.load(r)


def daily_curve(con):
    rows = list(con.execute("SELECT ts,cash,total_value,assets_total FROM portfolio_snapshot ORDER BY ts"))
    cut = datetime.datetime(2026, 7, 20).timestamp()
    rs = [r for r in rows if r["ts"] >= cut]
    from collections import defaultdict
    days = defaultdict(list)
    for r in rs:
        d = datetime.datetime.fromtimestamp(r["ts"], datetime.timezone.utc).strftime("%m-%d")
        days[d].append(r)
    out = []
    for d in sorted(days):
        g = days[d]
        a = [x["assets_total"] for x in g]
        out.append({"day": d, "open": g[0]["assets_total"], "hi": max(a), "lo": min(a),
                    "close": g[-1]["assets_total"], "cash": g[-1]["cash"]})
    return out


def collect(report_date):
    hold = fetch_holdings()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    s2t = {}
    for r in con.execute("SELECT DISTINCT slug,title FROM auto_reeval_suggestions WHERE title IS NOT NULL"):
        s2t.setdefault(r["slug"], r["title"])
    for r in con.execute("SELECT DISTINCT slug,title FROM auto_candidates WHERE title IS NOT NULL"):
        s2t.setdefault(r["slug"], r["title"])

    closed = []
    for r in con.execute(
        "SELECT market_slug,side,avg_entry_price,exit_price,size,realized_pnl_usd,exit_reason,"
        "stop_loss_tier,exit_at FROM closed_positions WHERE exit_at>=? ORDER BY realized_pnl_usd",
        (SINCE,)
    ):
        d = dict(r)
        d["label"] = llabel(r["market_slug"], s2t.get(r["market_slug"], ""))
        d["ret"] = ((r["exit_price"] - r["avg_entry_price"]) / r["avg_entry_price"]
                    if r["avg_entry_price"] else 0.0)
        d["kind"] = classify_exit(r["exit_reason"])
        d["why"] = why(r["market_slug"])
        d["cost"] = (r["size"] or 0) * (r["avg_entry_price"] or 0)
        closed.append(d)
    curve = daily_curve(con)
    con.close()

    losers = [c for c in closed if (c["realized_pnl_usd"] or 0) < 0]
    winners = sorted([c for c in closed if (c["realized_pnl_usd"] or 0) > 0],
                     key=lambda c: -c["realized_pnl_usd"])
    for p in hold["positions"]:
        p["ret"] = ((p["cur_price"] - p["avg_price"]) / p["avg_price"]) if p["avg_price"] else 0.0
    under = sorted([p for p in hold["positions"] if p["pnl_dollar"] < 0], key=lambda p: p["pnl_dollar"])

    return {
        "date": report_date,
        "acc": {k: hold[k] for k in ("assets_total", "cash", "position_count", "total_value", "total_pnl")},
        "closed": closed, "losers": losers, "winners": winners, "under": under,
        "loss_sum": sum(c["realized_pnl_usd"] for c in losers),
        "win_sum": sum(c["realized_pnl_usd"] for c in winners),
        "net": sum(c["realized_pnl_usd"] for c in closed),
        "curve": curve,
    }


SUPP_CSS = """
.buckets{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:6px 0 4px; }
.bk{ border-radius:12px; padding:14px 16px; }
.bk.a{ background:#fdecec; border:1px solid #f4cccc; }
.bk.b{ background:#fff6e8; border:1px solid #f3dfb8; }
.bk .bt{ font-size:11px; font-weight:800; margin-bottom:3px; }
.bk.a .bt{ color:var(--neg); } .bk.b .bt{ color:#b7791f; }
.bk .bn{ font-size:26px; font-weight:800; letter-spacing:-1px; color:var(--ink); }
.bk .bd{ font-size:10px; color:var(--ink2); margin-top:5px; }
.bk .bd b{ color:var(--ink); }
.evt{ text-align:left!important; white-space:normal!important; max-width:250px; font-size:9px; color:var(--ink2); line-height:1.45; }
table.det td{ vertical-align:top; }
.curve td.hi{ color:var(--pos); } .curve td.lo{ color:var(--neg); }
.arrowdown{ color:var(--neg); font-weight:800; }
"""


def det_rows(rows, pnl_label="亏$"):
    out = []
    for c in rows:
        v = c["realized_pnl_usd"] or 0
        out.append(
            f'<tr><td class="{cls(v)} num strong">{money(v)}</td>'
            f'<td>{c["side"]}</td>'
            f'<td>{tier_badge(c["stop_loss_tier"])}</td>'
            f'<td class="num dim">{c["avg_entry_price"]:.3f}→{c["exit_price"]:.3f}</td>'
            f'<td class="{cls(c["ret"])} num">{pct(c["ret"])}</td>'
            f'<td class="num dim">{c["size"]:.0f}股</td>'
            f'<td class="ek ek-{c["kind"]}">{c["kind"]}</td>'
            f'<td class="num dim">{c["exit_at"][5:16].replace("T"," ")}</td>'
            f'<td class="lbl">{c["label"]}</td>'
            f'<td class="evt">{c["why"] or "—"}</td></tr>'
        )
    return "\n".join(out)


def build_html(D):
    acc = D["acc"]
    now = acc["assets_total"]
    dd = now - PEAK
    giveback = dd - D["net"]   # 回撤 - 已实现 = 浮盈回吐(mark-to-market)
    curve_rows = "\n".join(
        f'<tr><td class="lbl">{c["day"]}</td><td class="num">${c["open"]:.2f}</td>'
        f'<td class="num hi">${c["hi"]:.2f}</td><td class="num lo">${c["lo"]:.2f}</td>'
        f'<td class="num strong">${c["close"]:.2f}</td><td class="num dim">${c["cash"]:.2f}</td></tr>'
        for c in D["curve"]
    )
    kpis = [
        ("峰值总资产", f"${PEAK:.2f}", "07-20", ""),
        ("现在总资产", f"${now:.2f}", D["date"][5:], ""),
        ("本轮回撤", money(dd), "峰值→现在", cls(dd)),
        ("其中·割肉净额", money(D["net"]), "已实现", cls(D["net"])),
        ("其中·浮盈回吐", money(giveback), "纸面利润没了", cls(giveback)),
    ]
    kpi_html = "\n".join(
        f'<div class="kpi"><div class="kl">{l}</div><div class="kv {c}">{v}</div>'
        f'<div class="kd"><span class="chip zero">{d}</span></div></div>'
        for l, v, d, c in kpis
    )

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>report_loss.html</title>
<style>{CSS}{SUPP_CSS}</style></head><body>

<header class="cover">
  <div class="eyebrow">POLYMARKET · 全自动账户 · 专项复盘</div>
  <h1>大亏损复盘报告</h1>
  <div class="sub">聚焦 <b>2026-07-20 峰值 $106 → {D['date']} ${now:.0f}</b> 这轮回撤 · 生成于 <b>{D['date']}</b> · 版本 v8.3.1 · <b>无任何出入金，全部为交易变动</b> · 本报告只读</div>
  <div class="kpis">{kpi_html}</div>
</header>

<section class="callout">
  <div class="co-h"><span class="pin">🔍</span> 一句话：钱没"亏光"，是"到嘴的利润又吐回去了"＋一波连环割肉</div>
  <p>峰值 $106 到现在 ${now:.0f}，掉了 <b class="neg">{money(dd)}</b>，<b>没有出金</b>，全是交易。拆成两块看 —— 割肉是"真金没了"，回吐是"赚到过没落袋"：</p>
  <div class="buckets">
    <div class="bk a">
      <div class="bt">① 真金割肉（已实现）</div>
      <div class="bn neg">{money(D['net'])}</div>
      <div class="bd">但底下是血战：<b class="neg">{len(D['losers'])} 笔止损 {money(D['loss_sum'])}</b> 被 <b class="pos">{len(D['winners'])} 笔止盈 {money(D['win_sum'])}</b> 补回来。净额小，不代表没打仗。</div>
    </div>
    <div class="bk b">
      <div class="bt">② 浮盈回吐（纸面）· 大头</div>
      <div class="bn neg">{money(giveback)}</div>
      <div class="bd">07-20 冲上 $106 是一堆仓的<b>纸面</b>利润；这两天跌回去了。⚠️ 但手上仓<b>现在仍比成本高 {money(acc['total_pnl'])}</b> —— 这不是亏进本金，是<b>赚到过、没卖、又还回去</b>。</div>
    </div>
  </div>
  <table class="grid curve" style="margin-top:10px">
    <thead><tr><th>日期</th><th>开盘</th><th>最高</th><th>最低</th><th>收盘</th><th>现金(收)</th></tr></thead>
    <tbody>{curve_rows}</tbody>
  </table>
  <p class="mini" style="margin-top:6px"><b class="arrowdown">↓</b> 痛点集中在 <b>07-21（$106→$98）和 07-22（$100→$92）两天</b>，连着两天割肉 + 回吐。</p>
</section>

<section class="break">
  <h2><span class="n">1</span> 割肉仓位全明细 <em>（{len(D['losers'])} 笔，合计 <b class="neg">{money(D['loss_sum'])}</b>；含标签/入场价/股数/事件）</em></h2>
  <table class="grid det closed">
    <thead><tr><th>亏$</th><th>方向</th><th>止损档</th><th>入场→卖出</th><th>收益率</th><th>股数</th><th>平仓方式</th><th>平仓时刻</th><th>市场</th><th>事件原因（为什么走反）</th></tr></thead>
    <tbody>{det_rows(D['losers'])}</tbody>
  </table>
  <p class="mini danger">规律很扎眼：<b>12 笔里 9 笔是 NO 单</b>，绝大多数是「押某事不会发生 / 冷门区间押反」→ 结果事件真发生了（要见 Netanyahu、俄军进 Vasylivka、GPT-6 发布升温…）。新止损把它们砍得又快又干净（好事），<b>但错的是上游方向</b>。</p>
</section>

<section class="break">
  <h2><span class="n">2</span> 对冲掉一半的止盈 <em>（{len(D['winners'])} 笔，合计 <b class="pos">{money(D['win_sum'])}</b>）</em></h2>
  <table class="grid det closed">
    <thead><tr><th>赚$</th><th>方向</th><th>止损档</th><th>入场→卖出</th><th>收益率</th><th>股数</th><th>平仓方式</th><th>平仓时刻</th><th>市场</th><th>事件原因（为什么赚）</th></tr></thead>
    <tbody>{det_rows(D['winners'])}</tbody>
  </table>
  <p class="mini">最大一笔 <b>Trump 在 Truth 发「World Cup」+$2.20</b>（方向全中、及时止盈落袋）。这些说明：<b>方向对 + 及时落袋</b>是能赚的；问题出在没落袋的那批（见回吐）和方向押反的那批（见割肉）。</p>
</section>

<section class="break">
  <h2><span class="n">3</span> 现在还套着的仓 <em>（{len(D['under'])} 仓，合计浮亏 {money(sum(p['pnl_dollar'] for p in D['under']))}；下一批止损候选）</em></h2>
  <table class="grid">
    <thead><tr><th>市场</th><th>方向</th><th>浮亏$</th><th>价格收益</th><th>入场→现价</th><th>q</th><th>止损档</th><th>状态</th></tr></thead>
    <tbody>{"".join(f'<tr><td class="lbl">{label("", p["title"])}</td><td>{p["side"]}</td><td class="neg num strong">{money(p["pnl_dollar"])}</td><td class="neg num">{pct(p["ret"])}</td><td class="num dim">{p["avg_price"]:.3f}→{p["cur_price"]:.3f}</td><td class="num dim">{p["q"]:.2f}</td><td>{tier_badge(p["stop_loss_tier"])}</td><td class="st">{p["monitor_state"]}</td></tr>' for p in D['under'])}</tbody>
  </table>
  <p class="mini">浮亏都不大（最深 Israel 领空 NO −12.7%）。若继续走反，事件型跌破 −50% / 收敛综合回撤到线，会被新止损自动平掉，不用手动盯。</p>
</section>

<section class="break">
  <h2><span class="n">4</span> 我对这次大亏损的分析</h2>
  <div class="two">
    <div class="card"><div class="ch">① 止损其实"救了场"，不是"闯的祸"</div>
      <p class="mini">这波 STOP_LOSS 把 Netanyahu(−$1.73)、Warsh(−$1.71)、Vasylivka(−$1.05) 这些方向押反的仓<b>又快又干净地砍掉</b>，没让它们变成第二个 Gemini（−76%）。割肉侧 {money(D['loss_sum'])} 听着吓人，但<b>每笔都是及时止血</b>——这正是上周刚上的硬止损在干活。</p>
    </div>
    <div class="card"><div class="ch">② 真正的病：上游选品方向系统性押反</div>
      <p class="mini">12 笔割肉 <b>9 笔 NO</b>，清一色「押某事不会发生」被现实打穿。这跟你之前问的<b>GLM 选品准确率</b>是同一个根 —— 止损再利索，也只是替糟糕的选品<b>兜底</b>，救不回方向本身。冷门量化盘（地震次数、汇率区间、Warsh 说不说某词）GLM 尤其没边际。</p>
    </div>
    <div class="card"><div class="ch">③ 最大的钱其实丢在"没落袋"上（{money(giveback)}）</div>
      <p class="mini">割肉净额才 {money(D['net'])}，回撤的大头是<b>纸面利润回吐 {money(giveback)}</b>。07-20 一堆仓冲到高位（$106），系统<b>没有在高位保护/落袋</b>，眼看又跌回来。止盈只在触发 0.92/翻倍那种硬线才动，中间的大幅回撤不管。</p>
    </div>
    <div class="card"><div class="ch">④ 换手太密，小额空转</div>
      <p class="mini">3 天平了 23 笔、还开了一批新仓，现金从 $33 打到 $9。里面不少是 ±$0.13~0.45 的小额重评离场，<b>产出接近 0 却每次吃价差</b>。高频小进小出把边际磨掉了。</p>
    </div>
  </div>
</section>

<section class="break">
  <h2><span class="n">5</span> 改进策略（按对这次亏损的针对性排序）</h2>
  <div class="rec todo"><div class="rh">🎯 直击最大亏损源（回吐 {money(giveback)}）</div>
    <ul>
      <li><b>① 给盈利仓加"移动止盈/高位保护"</b>（最关键）：一个仓涨到 +X%（比如 +25%）后，挂一条<b>跟随高点回撤 N% 就落袋</b>的线，把利润锁住。这轮 $106 若有这条，能保住大半回吐的钱。<span class="dim">（这是本次唯一直击"回吐"的措施，幅度你定）</span></li>
      <li><b>② 账户级总回撤闸</b>（上版就建议、仍没做）：从峰值回撤 &gt; $N 或 &gt;X% → 暂停开新仓 + 报警。$106→$93 这种滑坡本该被它拦一下。</li>
    </ul>
  </div>
  <div class="rec todo"><div class="rh">🧭 治上游（选品方向押反）</div>
    <ul>
      <li><b>③ 临近到期的 NO 单加约束</b>：9/12 割肉是「押不会发生」在事件逼近时被打穿。可对<b>剩余天数少、且盘口正在朝反方向走</b>的 NO 单收紧（少下 / 更快认输）。</li>
      <li><b>④ 冷门量化盘拉黑或降权</b>：地震次数、汇率区间、"某人会不会说某词"这类 GLM 没边际的盘，连亏且贡献 untitled 那类亏损，考虑排除或只进测试仓。</li>
    </ul>
  </div>
  <div class="rec todo"><div class="rh">🧹 减磨损</div>
    <ul>
      <li><b>⑤ 抬高浅水重评离场门槛</b>：±$0.5 以内的小额重评 exit 别做，省价差+API；让小波动自己走，别高频进出。</li>
    </ul>
  </div>
  <p class="mini" style="margin-top:8px"><b>一句话总览</b>：止损没错、反而立功；这次亏在 ①高位没落袋（回吐 {money(giveback)}）＋②选品方向押反（割肉 {money(D['loss_sum'])}）。<b>最高性价比的一步 = 给盈利仓加移动止盈</b>，直接堵住最大的窟窿。以上都可先纸面确认，我不擅自动钱/改参数。</p>
</section>

<footer>
  数据源：实时 <code>/api/auto/holdings</code> + <code>v4.db</code>（closed_positions 平仓明细 / portfolio_snapshot 资产曲线）。回撤 = 峰值 assets_total($106,07-20) − 现在；割肉净额 = 07-20 后 closed_positions 已实现累计；浮盈回吐 = 回撤 − 割肉净额（即纸面 mark-to-market 变动）。事件原因为人工标注。<b>本报告只读，未触碰任何仓位或参数。</b>
  <span class="gen">Polymarket AUTO v8.3.1 · 亏损复盘 · 生成于 {D['date']}</span>
</footer>
</body></html>"""


def main():
    report_date = sys.argv[1] if len(sys.argv) > 1 else "2026-07-23"
    D = collect(report_date)
    out = os.path.join(ROOT, "report_loss.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_html(D))
    print(f"HTML -> {out}")
    print(f"峰值 ${PEAK} → 现在 ${D['acc']['assets_total']:.2f} | 回撤 {money(D['acc']['assets_total']-PEAK)}")
    print(f"割肉净 {money(D['net'])} ({len(D['losers'])}亏{money(D['loss_sum'])}/{len(D['winners'])}盈+{D['win_sum']:.2f}) | "
          f"回吐 {money(D['acc']['assets_total']-PEAK-D['net'])} | 现套 {len(D['under'])}仓")


if __name__ == "__main__":
    main()
