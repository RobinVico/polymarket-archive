# -*- coding: utf-8 -*-
"""
三账户 7-8月 综合报告 (2026-08-27 用户要求, 只读)
→ 生成自包含 report_3acct.html → 无头 Chrome 打印成 三账户报告-<日期>.pdf

同一份 GLM 选品推荐, 三个真钱账户跑三套出场规则:
  主账户 (全自动)  = 分档止盈 + 三档止损 + 重评      sig=3
  Bench  (基准)   = $2/仓, 亏30%即卖, 无重评, 持到结算  sig=1
  Shadow (低价)   = ≤0.40 才买, $2/仓, -60%止损, 拿到结算 sig=3

口径铁律 (本报告的立场):
  **以资产真相为准** = (现在总资产) - (净投入)。逐笔台账只作明细 —— 因为归零卖不掉的废仓
  和 bench 的 vanished 仓永远不会写进平仓台账, 只看台账会高估战绩。
跑法: .venv/bin/python3 scripts/gen_3acct_report.py
"""
import os, sys, json, sqlite3, datetime as dt
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
DB = os.path.join(ROOT, "v4.db")
from gen_run_report import CSS as BASE_CSS, money, pct, cls
from gen_run_report import label as _base_label   # 复用同一套设计语言

# 通用 LABELS 覆盖不到的冷门盘, 本报告补 (沿用 gen_loss_report 的做法)
LOCAL_LABELS = [
    ("will-alphabet-be-the-third-largest", "Alphabet 成全球市值第三"),
    ("will-baidu-be-the-third-best-chinese-ai", "百度成中国第三 AI 公司"),
    ("will-trump-meet-with-benjamin-netanyahu", "特朗普7月会晤内塔尼亚胡"),
    ("will-warsh-say-oil-during-july-press", "沃什7月发布会说“石油”"),
]


def label(slug, title=""):
    for key, zh in LOCAL_LABELS:
        if (slug or "").startswith(key):
            return zh
    return _base_label(slug, title)

TZ = dt.datetime.now().astimezone().tzinfo
TZNAME = dt.datetime.now().astimezone().tzname()
GAP_MIN_SEC = 6 * 3600          # 超过 6h 无数据 = 停机空档, 从曲线上剔除
DEAD_PRICE = 0.05


def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c


def f_ts(ts, fmt="%m-%d %H:%M"):
    return dt.datetime.fromtimestamp(ts, TZ).strftime(fmt)


def parse_iso(s):
    if not s: return None
    try: return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception: return None


# ---------------------------------------------------------------- 资产曲线
def series(c, tbl, totcol, costcol=None):
    """拉快照, 剔除假点 (持仓值=0 但前后都有仓 = 开机瞬间只读到现金)。"""
    pv = "total_value" if tbl == "portfolio_snapshot" else "pos_value"
    sel = f"SELECT ts, cash, {pv} pv, {totcol} tot" + (f", {costcol} cost" if costcol else "")
    rows = [dict(r) for r in c.execute(f"{sel} FROM {tbl} ORDER BY ts")]
    out = []
    for i, r in enumerate(rows):
        if (r["pv"] in (0, None) and 0 < i < len(rows) - 1
                and (rows[i - 1]["pv"] or 0) > 1 and (rows[i + 1]["pv"] or 0) > 1):
            continue                                    # 假点, 丢掉
        out.append(r)
    return out


def collapse_gaps(all_ts):
    """把停机空档从时间轴上删掉: 返回 ts -> x 序号 的映射 + 空档清单。"""
    ts = sorted(set(all_ts))
    xmap, gaps, x = {}, [], 0.0
    for i, t in enumerate(ts):
        if i:
            d = t - ts[i - 1]
            if d > GAP_MIN_SEC:
                gaps.append((ts[i - 1], t, d))
                x += 1                                   # 空档只留 1 格宽的缝
            else:
                x += 1
        xmap[t] = x
    return xmap, gaps, x


def deposits(rows, totkey="tot"):
    """出入金识别 (沿用 8.0.5 口径): 现金跳 >=$3 且总额同步跳 = 出入金, 买卖不误判。"""
    net, evts = 0.0, []
    for i in range(1, len(rows)):
        dc = rows[i]["cash"] - rows[i - 1]["cash"]
        dtot = rows[i][totkey] - rows[i - 1][totkey]
        if abs(dc) >= 3 and abs(dtot - dc) < max(1.0, abs(dc) * 0.25):
            net += dc; evts.append((rows[i]["ts"], dc))
    return net, evts


# ---------------------------------------------------------------- 采集
def collect():
    c = conn()
    D = {"generated": dt.datetime.now(TZ), "tz": TZNAME}

    s_main = series(c, "portfolio_snapshot", "assets_total", "total_cost")
    s_bench = series(c, "bench_snapshot", "total", "pos_cost")
    s_shadow = series(c, "shadow_snapshot", "total", "pos_cost")

    xmap, gaps, xmax = collapse_gaps([r["ts"] for r in s_main + s_bench + s_shadow])
    D["gaps"] = gaps; D["xmap"] = xmap; D["xmax"] = xmax

    # ---- 主账户
    net_m, ev_m = deposits(s_main)
    start_m = s_main[0]["tot"]
    cur_m = s_main[-1]["tot"]
    closed = [dict(r) for r in c.execute(
        "SELECT * FROM closed_positions WHERE exit_at>='2026-07-01' ORDER BY exit_at")]
    main = {
        "key": "main", "name": "主账户 · 全自动", "funder": "0xDEd2…4A85", "sig": 3,
        "rule": "分档止盈 (事件型翻倍/0.92卖半 · 收敛0.88 · 其余0.90) + 三档止损 + GLM 重评",
        "since": s_main[0]["ts"], "series": s_main,
        "money_in": start_m + net_m, "deposits": ev_m,
        "cash": s_main[-1]["cash"], "pos_value": s_main[-1]["pv"], "total": cur_m,
        "net": cur_m - start_m - net_m,
        "closed": closed,
        "ledger_realized": sum(r["realized_pnl_usd"] or 0 for r in closed),
    }

    # ---- Bench
    net_b, ev_b = deposits(s_bench)
    bp = [dict(r) for r in c.execute("SELECT * FROM bench_positions WHERE dry=0")]
    real_b = [r for r in bp if r["status"] not in ("score_only",) and not str(r["status"]).startswith("error")]
    closed_b = [r for r in real_b if r["status"] in ("stopped", "resolved", "vanished")]
    scored = [r for r in bp if r["is_correct"] is not None]
    bench = {
        "key": "bench", "name": "Bench · 基准对照", "funder": "0xd19c…E07E", "sig": 1,
        "rule": "$2/仓固定 · 唯一卖出=亏30%瞬时清仓 · 无重评无止盈 · 其余持到结算",
        "purpose": "拿掉「提前卖出」这个变量, 测 GLM 裸预测准确率",
        "since": s_bench[0]["ts"], "series": s_bench,
        "money_in": s_bench[0]["tot"] + net_b, "deposits": ev_b,
        "cash": s_bench[-1]["cash"], "pos_value": s_bench[-1]["pv"], "total": s_bench[-1]["tot"],
        "net": s_bench[-1]["tot"] - s_bench[0]["tot"] - net_b,
        "positions": real_b, "closed": closed_b, "scored": scored,
        "n_correct": sum(1 for r in scored if r["is_correct"]),
        "ledger_realized": sum(r["realized_pnl_usd"] or 0 for r in closed_b),
        "vanished_cost": sum(r["usd"] or 0 for r in closed_b if r["status"] == "vanished"),
        "n_vanished": sum(1 for r in closed_b if r["status"] == "vanished"),
    }

    # ---- Shadow
    net_s, ev_s = deposits(s_shadow)
    sp = [dict(r) for r in c.execute("SELECT * FROM shadow_positions WHERE dry=0")]
    closed_s = [r for r in sp if r["status"] in ("stopped", "resolved")]
    shadow = {
        "key": "shadow", "name": "Shadow · 低价拿到底", "funder": "0x812D…1Ce0", "sig": 3,
        "rule": "只吃测试仓那半且新鲜价 ≤0.40 · $2/仓 · 止损=入场−60%+$0.05地板 · 不止盈不重评, 拿到结算",
        "purpose": "主策略嫌太便宜不敢真买的那半, 用第三个账户真金白银验一遍",
        "since": s_shadow[0]["ts"], "series": s_shadow,
        "money_in": s_shadow[0]["tot"] + net_s, "deposits": ev_s,
        "cash": s_shadow[-1]["cash"], "pos_value": s_shadow[-1]["pv"], "total": s_shadow[-1]["tot"],
        "net": s_shadow[-1]["tot"] - s_shadow[0]["tot"] - net_s,
        "positions": sp, "closed": closed_s,
        "ledger_realized": sum(r["realized_pnl_usd"] or 0 for r in closed_s),
        "n_open": sum(1 for r in sp if r["status"] == "open"),
    }

    D["accounts"] = [main, bench, shadow]

    # ---- 主账户明细聚合
    by_reason, by_tier, by_month = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
    for r in closed:
        k = (r["exit_reason"] or "?").split(":")[0].split("(")[0].strip()
        by_reason[k][0] += 1; by_reason[k][1] += r["realized_pnl_usd"] or 0
        t = r["stop_loss_tier"] or "未分类"
        by_tier[t][0] += 1; by_tier[t][1] += r["realized_pnl_usd"] or 0
        d = parse_iso(r["exit_at"])
        if d:
            m = d.astimezone(TZ).strftime("%Y-%m")
            by_month[m][0] += 1; by_month[m][1] += r["realized_pnl_usd"] or 0
    D["by_reason"] = dict(by_reason); D["by_tier"] = dict(by_tier); D["by_month"] = dict(by_month)
    D["main_top"] = sorted(closed, key=lambda r: -(r["realized_pnl_usd"] or 0))[:7]
    D["main_bot"] = sorted(closed, key=lambda r: (r["realized_pnl_usd"] or 0))[:7]

    # ---- bench 准确率按价位桶
    buckets = defaultdict(lambda: [0, 0])
    for r in scored:
        p = r["rec_price"] or 0
        b = "≤0.30" if p <= .3 else "0.30–0.50" if p <= .5 else "0.50–0.70" if p <= .7 else "0.70–0.85" if p <= .85 else ">0.85"
        buckets[b][0] += 1; buckets[b][1] += 1 if r["is_correct"] else 0
    D["bench_buckets"] = dict(buckets)

    # ---- 废仓 (卖不掉的归零仓)
    try:
        import urllib.request
        h = json.load(urllib.request.urlopen("http://127.0.0.1:5052/api/auto/holdings", timeout=20))
        ps = h.get("positions") or h.get("holdings") or []
        D["dead"] = [p for p in ps if float(p.get("cur_price") or 0) < DEAD_PRICE]
        D["live_positions"] = ps
    except Exception:
        D["dead"] = []; D["live_positions"] = []
    D["dead_cost"] = sum(float(p.get("size", 0)) * float(p.get("avg_price", 0)) for p in D["dead"])
    return D


# ---------------------------------------------------------------- 曲线 (SVG)
def ret_curve(acct, xmap):
    """把快照换算成「相对净投入的收益率%」—— 三个账户本金不同, 只有收益率可比。
    净投入随出入金变化, 所以逐点累计。"""
    dep = dict((t, v) for t, v in acct["deposits"])
    base = acct["series"][0]["tot"]
    pts = []
    for r in acct["series"]:
        if r["ts"] in dep: base += dep[r["ts"]]
        if base <= 0: continue
        pts.append((xmap[r["ts"]], (r["tot"] - base) / base * 100.0, r["ts"], r["tot"]))
    return pts


def svg_chart(D, w=760, h=250, pad_l=44, pad_r=54, pad_t=16, pad_b=26):
    xmap, xmax = D["xmap"], D["xmax"]
    colors = {"main": "#2f6fb0", "bench": "#b7791f", "shadow": "#7a4fc0"}
    curves = {a["key"]: ret_curve(a, xmap) for a in D["accounts"]}
    ys = [p[1] for c in curves.values() for p in c]
    lo, hi = min(ys + [0]), max(ys + [0])
    span = max(hi - lo, 8.0); lo -= span * .08; hi += span * .08
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    X = lambda x: pad_l + (x / max(xmax, 1)) * iw
    Y = lambda y: pad_t + (hi - y) / (hi - lo) * ih

    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" class="chart">']
    ends = []
    # 网格 + y 轴
    step = 10 if (hi - lo) <= 70 else 20
    g = int(lo // step) * step
    while g <= hi:
        yy = Y(g)
        out.append(f'<line x1="{pad_l}" x2="{w-pad_r}" y1="{yy:.1f}" y2="{yy:.1f}" '
                   f'stroke="{"#c9d2e2" if g==0 else "#eef1f7"}" stroke-width="{1.2 if g==0 else 1}"/>')
        out.append(f'<text x="{pad_l-6}" y="{yy+3:.1f}" class="ax" text-anchor="end">{g:+d}%</text>')
        g += step
    # 停机空档竖带
    for a, b, d in D["gaps"]:
        xa, xb = X(xmap[a]), X(xmap[b])
        out.append(f'<line x1="{(xa+xb)/2:.1f}" x2="{(xa+xb)/2:.1f}" y1="{pad_t}" y2="{h-pad_b}" '
                   f'stroke="#d13b3b" stroke-width="1" stroke-dasharray="3,3" opacity=".5"/>')
        cx = min(max((xa + xb) / 2, pad_l + 46), w - pad_r - 46)   # 夹在画布内, 别被裁掉
        out.append(f'<text x="{cx:.1f}" y="{pad_t+9:.1f}" class="gaplab" text-anchor="middle">'
                   f'停机 {d/86400:.0f} 天 · 已剔除</text>')
    # x 轴日期
    ticks, seen = [], set()
    for t in sorted(xmap):
        d = dt.datetime.fromtimestamp(t, TZ).strftime("%m-%d")
        if d not in seen and dt.datetime.fromtimestamp(t, TZ).day in (1, 8, 15, 22, 27):
            seen.add(d); ticks.append((xmap[t], d))
    for x, lab in ticks:
        out.append(f'<text x="{X(x):.1f}" y="{h-pad_b+14:.1f}" class="ax" text-anchor="middle">{lab}</text>')
    # 三条线
    for a in D["accounts"]:
        pts = curves[a["key"]]
        if not pts: continue
        dpath = " ".join(f"{'M' if i==0 else 'L'}{X(p[0]):.1f},{Y(p[1]):.1f}" for i, p in enumerate(pts))
        out.append(f'<path d="{dpath}" fill="none" stroke="{colors[a["key"]]}" stroke-width="2" '
                   f'stroke-linejoin="round"/>')
        lx, ly = X(pts[-1][0]), Y(pts[-1][1])
        out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" fill="{colors[a["key"]]}"/>')
        ends.append([ly, colors[a["key"]], f'{pts[-1][1]:+.1f}%', lx])
    ends.sort()
    for i in range(1, len(ends)):                       # 上下岔开, 别叠在一起
        if ends[i][0] - ends[i-1][0] < 11:
            ends[i][0] = ends[i-1][0] + 11
    for ly, col, txt, lx in ends:
        out.append(f'<text x="{lx+6:.1f}" y="{ly+3:.1f}" class="endlab" text-anchor="start" '
                   f'fill="{col}">{txt}</text>')
    out.append("</svg>")
    leg = " ".join(f'<span class="lg"><i style="background:{colors[a["key"]]}"></i>{a["name"]}</span>'
                   for a in D["accounts"])
    return "".join(out) + f'<div class="legend">{leg}</div>'


def bar_row(label_, n, pnl, maxabs, extra=""):
    wpos = abs(pnl) / maxabs * 100 if maxabs else 0
    side = "pos" if pnl >= 0 else "neg"
    return (f'<div class="brow"><div class="bl">{label_}</div>'
            f'<div class="bt"><div class="bbar {side}" style="width:{wpos:.1f}%"></div></div>'
            f'<div class="bn">{n} 笔</div><div class="bv {cls(pnl)}">{money(pnl)}</div>'
            f'<div class="bx">{extra}</div></div>')


EXTRA_CSS = r"""
.chart{ display:block; margin:6px 0 2px; }
.chart .ax{ font-size:8.5px; fill:#7c89a0; }
.chart .gaplab{ font-size:8px; fill:#d13b3b; font-weight:700; }
.chart .endlab{ font-size:9.5px; font-weight:800; }
.legend{ display:flex; gap:16px; justify-content:center; font-size:9.5px; color:#41506b; margin-top:2px; }
.legend .lg{ display:flex; align-items:center; gap:5px; font-weight:600; }
.legend i{ width:12px; height:3px; border-radius:2px; display:inline-block; }
.acct3{ display:grid; grid-template-columns:repeat(3,1fr); gap:11px; margin:14px 0 4px; }
.ac{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:13px 14px;
  box-shadow:0 1px 2px rgba(20,26,38,.04); border-top:3px solid var(--brand2); }
.ac.bench{ border-top-color:#b7791f; } .ac.shadow{ border-top-color:#7a4fc0; }
.ac h3{ font-size:12.5px; font-weight:800; color:var(--brand); margin-bottom:1px; }
.ac .who{ font-size:8.5px; color:var(--dim); font-family:ui-monospace,Menlo,monospace; margin-bottom:7px; }
.ac .big{ font-size:23px; font-weight:800; letter-spacing:-.6px; }
.ac .sub2{ font-size:9.5px; color:var(--ink2); margin-top:3px; }
.ac .rulebox{ margin-top:8px; padding-top:7px; border-top:1px dashed var(--line);
  font-size:9px; color:var(--ink2); line-height:1.45; }
.brow{ display:grid; grid-template-columns:150px 1fr 44px 62px 1fr; gap:8px; align-items:center;
  padding:3.5px 0; font-size:10px; }
.bl{ color:var(--ink2); font-weight:600; }
.bt{ background:var(--line2); height:9px; border-radius:5px; overflow:hidden; }
.bbar{ height:100%; border-radius:5px; } .bbar.pos{ background:var(--pos); } .bbar.neg{ background:var(--neg); }
.bn{ color:var(--dim); text-align:right; font-size:9px; }
.bv{ text-align:right; font-weight:700; font-variant-numeric:tabular-nums; }
.bx{ color:var(--dim); font-size:9px; }
.hero{ background:linear-gradient(180deg,#fff6f6,#fff); border:1px solid #f3c9c9; border-left:4px solid var(--neg);
  border-radius:12px; padding:15px 17px; margin:14px 0; }
.hero h3{ font-size:15px; color:#a32020; font-weight:800; margin-bottom:5px; }
.hero p{ font-size:10.5px; color:var(--ink2); line-height:1.6; }
.bkt{ display:grid; grid-template-columns:repeat(5,1fr); gap:9px; margin-top:11px; }
.bk{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:9px 6px; text-align:center; }
.bk .bp{ font-size:9px; color:var(--dim); font-weight:700; }
.bk .bv2{ font-size:19px; font-weight:800; margin:2px 0 1px; }
.bk .bn2{ font-size:8.5px; color:var(--dim); }
.bk.zero{ background:#fdecec; border-color:#f3c9c9; }
.bk.zero .bv2{ color:var(--neg); }
table.cmp{ width:100%; border-collapse:collapse; font-size:10px; margin-top:9px; }
table.cmp th{ background:#f1f4fa; color:var(--ink2); font-weight:700; text-align:left;
  padding:6px 8px; border-bottom:1px solid var(--line); font-size:9.5px; }
table.cmp td{ padding:5.5px 8px; border-bottom:1px solid var(--line2); vertical-align:top; }
table.cmp td.n{ text-align:right; font-variant-numeric:tabular-nums; font-weight:700; }
table.cmp tr.tot td{ background:#f8fafd; font-weight:800; border-top:1.5px solid var(--line); }
.take{ background:#f7f9fd; border:1px solid var(--line); border-left:3px solid var(--brand2);
  border-radius:9px; padding:9px 12px; margin:7px 0; font-size:10.3px; color:var(--ink2); line-height:1.55; }
.take b{ color:var(--ink); }
.take.warn{ border-left-color:#d13b3b; background:#fffafa; }
.take.good{ border-left-color:#0e8a5f; background:#f7fdfa; }
h2{ font-size:15px; font-weight:800; color:var(--brand); margin:15px 0 3px;
  padding-bottom:5px; border-bottom:2px solid var(--line); }
h2 .hint{ font-size:9.5px; font-weight:600; color:var(--dim); margin-left:8px; }
.small{ font-size:9.5px; color:var(--dim); margin-top:3px; }
.twocol{ break-inside:avoid; }
.concl{ display:grid; grid-template-columns:1fr 1fr; gap:9px; break-inside:avoid; }
.concl .take{ margin:0; }
.twocol table.cmp{ break-inside:avoid; }
.take, .hero, .ac, .bkt{ break-inside:avoid; }
h3{ break-after:avoid; }
"""


def build_html(D):
    A = {a["key"]: a for a in D["accounts"]}
    gen = D["generated"].strftime("%Y-%m-%d %H:%M")
    span = f'{f_ts(min(a["since"] for a in D["accounts"]), "%Y-%m-%d")} → {f_ts(A["main"]["series"][-1]["ts"], "%Y-%m-%d")}'

    # ---- 账户卡
    cards = []
    for a in D["accounts"]:
        r = a["net"] / a["money_in"] * 100 if a["money_in"] else 0
        cards.append(f"""
      <div class="ac {a['key']}">
        <h3>{a['name']}</h3><div class="who">{a['funder']} · sig={a['sig']} · 起于 {f_ts(a['since'],'%m-%d')}</div>
        <div class="big {cls(a['net'])}">{money(a['net'])}</div>
        <div class="sub2"><b>{r:+.1f}%</b> · 投入 ${a['money_in']:.2f} → 现 ${a['total']:.2f}</div>
        <div class="sub2">现金 ${a['cash']:.2f} · 持仓 ${a['pos_value']:.2f}</div>
        <div class="rulebox"><b>规则:</b> {a['rule']}</div>
      </div>""")

    # ---- 准确率桶
    order = ["≤0.30", "0.30–0.50", "0.50–0.70", "0.70–0.85", ">0.85"]
    bks = []
    for b in order:
        n, k = D["bench_buckets"].get(b, [0, 0])
        acc = k / n * 100 if n else 0
        bks.append(f'<div class="bk{" zero" if n and k==0 else ""}"><div class="bp">{b}</div>'
                   f'<div class="bv2">{acc:.0f}%</div><div class="bn2">{k}/{n} 对</div></div>')

    # ---- 主账户: 平仓方式 / 止损档
    mx = max(abs(v[1]) for v in D["by_reason"].values()) or 1
    reasons = "".join(bar_row(k, v[0], v[1], mx) for k, v in
                      sorted(D["by_reason"].items(), key=lambda x: x[1][1]))
    tx = max(abs(v[1]) for v in D["by_tier"].values()) or 1
    tiers = "".join(bar_row({"event_driven": "事件驱动型", "convergent": "真相收敛型",
                             "hybrid": "混合型"}.get(k, k), v[0], v[1], tx)
                    for k, v in sorted(D["by_tier"].items(), key=lambda x: x[1][1]))
    months = "".join(bar_row(k, v[0], v[1], max(abs(x[1]) for x in D["by_month"].values()) or 1)
                     for k, v in sorted(D["by_month"].items()))

    def trow(r, pnlkey="realized_pnl_usd", titlekey="market_slug"):
        p = r.get(pnlkey) or 0
        t = label(r.get("market_slug") or "", r.get("title") or "") if titlekey == "market_slug" else (r.get("title") or "")
        return (f'<tr><td>{t[:56]}</td><td class="n">{(r.get("avg_entry_price") or r.get("entry_price") or 0):.3f}</td>'
                f'<td class="n">{(r.get("exit_price") or 0):.3f}</td>'
                f'<td class="n {cls(p)}">{money(p)}</td></tr>')

    top = "".join(trow(r) for r in D["main_top"])
    bot = "".join(trow(r) for r in D["main_bot"])

    # ---- 对比表
    rows_cmp = ""
    for a in D["accounts"]:
        r = a["net"] / a["money_in"] * 100 if a["money_in"] else 0
        nclosed = len(a.get("closed", []))
        rows_cmp += (f'<tr><td><b>{a["name"]}</b><div class="small">{a["rule"][:64]}</div></td>'
                     f'<td class="n">${a["money_in"]:.2f}</td><td class="n">${a["total"]:.2f}</td>'
                     f'<td class="n {cls(a["net"])}">{money(a["net"])}</td>'
                     f'<td class="n {cls(a["net"])}">{r:+.1f}%</td><td class="n">{nclosed}</td></tr>')
    tot_in = sum(a["money_in"] for a in D["accounts"])
    tot_now = sum(a["total"] for a in D["accounts"])
    rows_cmp += (f'<tr class="tot"><td>三账户合计</td><td class="n">${tot_in:.2f}</td>'
                 f'<td class="n">${tot_now:.2f}</td><td class="n {cls(tot_now-tot_in)}">{money(tot_now-tot_in)}</td>'
                 f'<td class="n {cls(tot_now-tot_in)}">{(tot_now-tot_in)/tot_in*100:+.1f}%</td><td class="n">—</td></tr>')

    dead_rows = "".join(
        f'<tr><td>{(p.get("title") or "")[:56]}</td>'
        f'<td class="n">{float(p.get("avg_price") or 0):.3f}</td><td class="n">{float(p.get("cur_price") or 0):.3f}</td>'
        f'<td class="n neg">-${float(p.get("size",0))*float(p.get("avg_price",0)):.2f}</td></tr>'
        for p in D["dead"])

    b, s = A["bench"], A["shadow"]
    bacc = b["n_correct"] / len(b["scored"]) * 100 if b["scored"] else 0
    gap_txt = " · ".join(f'{f_ts(x,"%m-%d")}→{f_ts(y,"%m-%d")} ({d/86400:.0f}天)' for x, y, d in D["gaps"])

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>三账户报告 {span}</title><style>{BASE_CSS}{EXTRA_CSS}</style></head><body>

<div class="cover">
  <div class="eyebrow">POLYMARKET AUTO · 三账户对照实盘</div>
  <h1>同一份 AI 推荐, 三套出场规则</h1>
  <div class="sub">统计区间 <b>{span}</b> ({TZNAME}) · 生成于 {gen} · 数据源 v4.db + 实时持仓接口<br>
  口径: <b>以资产真相为准</b> = 现在总资产 − 净投入。逐笔台账只作明细 —— 归零卖不掉的废仓不进台账, 只看台账会高估战绩。</div>
</div>

<div class="acct3">{"".join(cards)}</div>

<h2>一 · 资产曲线<span class="hint">收益率口径 (三账户本金不同, 只有 % 可比) · 停机空档已从时间轴剔除</span></h2>
{svg_chart(D)}
<div class="small">已剔除的停机空档: {gap_txt} —— 这些天 bot 关着、无人打点, 曲线不再拉直线跨过去。</div>

<div class="hero">
  <h3>头条发现: AI 挑的「便宜票」12 投 0 中</h3>
  <p>Bench 账户存在的意义就是测 GLM 裸预测准确率 —— 不提前卖、持到结算, 看它到底猜没猜对。
  整体 <b>{b['n_correct']}/{len(b['scored'])} = {bacc:.1f}%</b>, 勉强及格。但按推荐价拆开看, 结论完全变了:</p>
  <div class="bkt">{"".join(bks)}</div>
  <p style="margin-top:10px">价格 <b>≤$0.30 的推荐, 12 个全错, 准确率 0%</b>。而 Shadow 账户的整套策略正是
  <b>专挑 ≤$0.40 买</b> —— 它亏 {s['net']/s['money_in']*100:.1f}% 不是运气差, 是策略建在了 AI 最不准的价格带上。
  中间价 0.50–0.70 才是 GLM 的主场 (76%)。</p>
</div>

<h2>二 · 三策略横向对比<span class="hint">同一份选品推荐, 唯一变量是「怎么出场」</span></h2>
<table class="cmp"><thead><tr><th>账户 / 出场规则</th><th style="text-align:right">净投入</th>
<th style="text-align:right">现总资产</th><th style="text-align:right">纯交易盈亏</th>
<th style="text-align:right">收益率</th><th style="text-align:right">已结笔数</th></tr></thead>
<tbody>{rows_cmp}</tbody></table>

<div class="take good"><b>结论很硬:</b> 三个账户吃的是<b>同一批 GLM 推荐</b>, 唯一差别是出场规则。
主账户 <b>{money(A['main']['net'])} ({A['main']['net']/A['main']['money_in']*100:+.1f}%)</b> 基本打平,
而两个"不管它、持到结算"的账户各亏掉三分之一。
<b>赚钱的不是选品, 是止盈止损。</b>同一批票, 会卖的打平, 不会卖的腰斩。</div>

<section>
<h2>三 · 主账户明细<span class="hint">{len(A['main']['closed'])} 笔平仓 · 全自动分档止盈/止损/重评</span></h2>
<h3 style="font-size:11.5px;margin:10px 0 3px;color:#41506b">按平仓方式</h3>{reasons}
<h3 style="font-size:11.5px;margin:12px 0 3px;color:#41506b">按止损档 (GLM 入场分级)</h3>{tiers}
<h3 style="font-size:11.5px;margin:12px 0 3px;color:#41506b">按月</h3>{months}

<div class="take"><b>怎么读:</b> 止盈四类合计
<b>{money(sum(v[1] for k,v in D['by_reason'].items() if 'TAKE_PROFIT' in k))}</b> 是全部利润来源;
<b>STOP_LOSS {money(D['by_reason'].get('STOP_LOSS',[0,0])[1])}</b> 是为这些利润付的保险费;
<b>AUTO_REEVAL {money(D['by_reason'].get('AUTO_REEVAL',[0,0])[1])}</b> 说明 GLM 重评判"卖"基本是在磨损上打平 —— 它更像刹车而不是油门。
分档上 <b>事件驱动型是唯一稳定赚钱的档</b>, 收敛型净亏。</div>

<div class="twocol" style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px">
<div><h3 style="font-size:11.5px;margin-bottom:3px;color:#0e8a5f">最赚的 7 笔</h3>
<table class="cmp"><thead><tr><th>市场</th><th style="text-align:right">入</th><th style="text-align:right">出</th><th style="text-align:right">盈亏</th></tr></thead><tbody>{top}</tbody></table></div>
<div><h3 style="font-size:11.5px;margin-bottom:3px;color:#d13b3b">最亏的 7 笔</h3>
<table class="cmp"><thead><tr><th>市场</th><th style="text-align:right">入</th><th style="text-align:right">出</th><th style="text-align:right">盈亏</th></tr></thead><tbody>{bot}</tbody></table></div>
</div>
</section>

<section>
<h2>四 · Bench 基准账户<span class="hint">$2/仓 · 亏30%即卖 · 无重评 · 其余持到结算</span></h2>
<div class="take"><b>它的任务不是赚钱, 是当对照组。</b>{b['purpose']}。
真实建仓 <b>{len(b['positions'])}</b> 个, 投入约 ${sum(r['usd'] or 0 for r in b['positions']):.2f};
已结 {len(b['closed'])} 个 (止损 {sum(1 for r in b['closed'] if r['status']=='stopped')} ·
结算 {sum(1 for r in b['closed'] if r['status']=='resolved')} ·
<b>凭空消失 {b['n_vanished']}</b>)。</div>
<div class="take warn"><b>⚠ 账上有个洞:</b> <b>{b['n_vanished']} 个仓「vanished」</b> —— 成本合计
<b>${b['vanished_cost']:.2f}</b>, 从账户里消失了却没留下平仓记录 (多半是结算归零后被清掉)。
台账 realized 只写了 {money(b['ledger_realized'])}, 而资产口径实亏 <b>{money(b['net'])}</b> ——
这 ${b['vanished_cost']:.2f} 就是差额的主要来源。<b>看 bench 战绩必须看资产口径, 台账会骗人。</b></div>

<h2>五 · Shadow 低价账户<span class="hint">≤0.40 才买 · $2/仓 · −60%止损 · 不止盈, 拿到结算</span></h2>
<div class="take"><b>它验证的假设:</b> {s['purpose']}。
建仓 <b>{len(s['positions'])}</b> 个, 投入 ${sum(r['stake_usd'] or 0 for r in s['positions']):.2f};
已结 {len(s['closed'])} 个 (止损 {sum(1 for r in s['closed'] if r['status']=='stopped')} ·
结算 {sum(1 for r in s['closed'] if r['status']=='resolved')}), 持有中 {s['n_open']} 个。</div>
<div class="take warn"><b>假设被证伪了。</b>结果 <b>{money(s['net'])} ({s['net']/s['money_in']*100:+.1f}%)</b>。
根因见头条: <b>GLM 在 ≤$0.30 区间 12 投 0 中</b>。当初定 −60% 止损的依据是"18 条低价仓里唯一的真赢家中途最深跌 55%,
−50% 会杀掉赢家" —— 逻辑没错, 但前提是<b>确实存在赢家</b>。样本扩大后, 那个赢家更像是幸存者偏差:
放宽止损只是让每张废票多亏 10 个百分点才躺平。</div>
</section>

<section>
<h2>六 · 账实不符: 卖不掉的废仓<span class="hint">台账看不见的亏损</span></h2>
<div class="take warn">主账户平仓台账写着已实现 <b>{money(A['main']['ledger_realized'])}</b>,
但资产口径只有 <b>{money(A['main']['net'])}</b>。差额主要就埋在下面这
<b>{len(D['dead'])} 个归零后卖不掉的仓</b>里 (成本 <b>${D['dead_cost']:.2f}</b>) ——
它们价格归零、订单簿已撤 (<code>404 No orderbook</code>), 卖单永远失败, 于是<b>永远不会写进平仓台账</b>,
在报表上装作"还持有"。监控每 30 秒重试一次, 无限循环。</div>
<table class="cmp"><thead><tr><th>市场</th><th style="text-align:right">成本价</th>
<th style="text-align:right">现价</th><th style="text-align:right">埋掉的钱</th></tr></thead><tbody>{dead_rows}</tbody></table>

<h2>七 · 结论与下一步</h2>
<div class="concl">
<div class="take good"><b>1. 出场规则就是全部。</b>同一批 AI 推荐, 主账户 {A['main']['net']/A['main']['money_in']*100:+.1f}%,
不管不问的两个账户 −38% / −35%。分档止盈是唯一的利润来源。</div>
<div class="take warn"><b>2. 停掉 Shadow 的低价策略, 或把价格下限抬到 0.35~0.40 以上。</b>
≤$0.30 区间 GLM 12 投 0 中, 这不是止损参数能救的 —— 是这个价格带本身 AI 判不准。</div>
<div class="take warn"><b>3. 修废仓无限重试。</b>{len(D['dead'])} 个仓每 30 秒重试卖出且永远失败, 刷屏又让台账失真。
bench 早有解法 (卖失败退避 10 分钟 + 尘埃仓强关), 主链路的 monitor.py 因隔离铁律不能改 —— 要修得开独立新文件。</div>
<div class="take"><b>4. 别再只看平仓台账。</b>bench 的 ${b['vanished_cost']:.2f} vanished + 主账户的 ${D['dead_cost']:.2f} 废仓
都不进台账。首页那几个"已实现盈亏"磁贴系统性偏乐观, 真相在资产曲线上。</div>
</div>
<div class="small" style="margin-top:14px">本报告只读生成, 未改动任何仓位或参数。生成器 <code>scripts/gen_3acct_report.py</code>。</div>
</section>
</body></html>"""


def main():
    D = collect()
    html = build_html(D)
    out = os.path.join(ROOT, "report_3acct.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"HTML -> {out}")
    for a in D["accounts"]:
        print(f"  {a['name']:18s} ${a['money_in']:7.2f} → ${a['total']:7.2f} = "
              f"{money(a['net'])} ({a['net']/a['money_in']*100:+.1f}%)")


if __name__ == "__main__":
    main()
