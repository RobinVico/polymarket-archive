"""端到端自检 — 绝不下单, 只验证数据链路和规则.
用法: cd /Users/baymaxagent/天气 && .venv/bin/python scripts/selftest.py
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules.gamma_client import install_polymarket_dns_guard  # noqa: E402
install_polymarket_dns_guard()
from modules import config, db, decide, markets, wx  # noqa: E402
from modules.sunset import sunset_utc  # noqa: E402

TZ = timezone(timedelta(hours=8))
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))


def t_sunset():
    today = datetime.now(TZ).date()
    for key in ("hongkong", "chengdu"):
        cfg = config.CITIES[key]
        ours = sunset_utc(cfg["lat"], cfg["lon"], today, 8)
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={cfg['lat']}&longitude={cfg['lon']}"
               f"&daily=sunset&timezone=UTC&start_date={today}&end_date={today}")
        req = urllib.request.Request(url, headers={"User-Agent": "tianqi-bot/0.1"})
        ref = json.load(urllib.request.urlopen(req, timeout=20))["daily"]["sunset"][0]
        ref_dt = datetime.fromisoformat(ref).replace(tzinfo=timezone.utc)
        diff = abs((ours - ref_dt).total_seconds())
        check(f"日落[{cfg['name']}] 本地算 vs 权威API", diff <= 240,
              f"我们 {ours.astimezone(TZ):%H:%M} vs API {ref_dt.astimezone(TZ):%H:%M} (差 {diff/60:.1f} 分钟)")


def t_market():
    today = datetime.now(TZ).date()
    slug = markets.event_slug("shanghai", today)
    ev = markets.fetch_event(slug)
    ok = bool(ev and len(ev["buckets"]) >= 5)
    check("市场解析[上海] 档位数", ok, f"{len(ev['buckets']) if ev else 0} 档")
    if ok:
        b = markets.pick_bucket(ev["buckets"], 31)
        check("pick_bucket(31) 命中", b is not None, b["label"] if b else "")
        top = markets.top_bucket(ev["buckets"])
        check("市场共识档存在", top is not None,
              f"{top['label']} @ {top['yes_price']}" if top else "")
        if top and top.get("token_yes"):
            ask = markets.best_ask_public(top["token_yes"])
            check("CLOB 公开盘口卖一价", ask is not None and 0 < ask <= 1, f"ask={ask}")


def t_wx():
    db.init_db()
    m = {cfg["station"]: k for k, cfg in config.CITIES.items()
         if cfg["source"] == "metar" and cfg["enabled"]}
    n = wx.poll_metar(m)
    check("METAR 拉取入库", n > 0, f"{n} 条")
    n2 = wx.poll_hko()
    check("HKO 1分钟数据入库", n2 > 0, f"{n2} 条")
    today = datetime.now(TZ).date()
    st = wx.day_stats("shanghai", today)
    check("上海当日统计", st is not None and st["n"] >= 5,
          f"max={st['max']} cur={st['cur']} n={st['n']}" if st else "无数据")
    if st:
        first_h = datetime.fromtimestamp(st["first_ts"], TZ).hour
        check("上海当日覆盖完整 (首条≤11点)", first_h <= config.COVERAGE_BY_H, f"首条 {first_h} 点")


def t_guards():
    now_ts = 1_800_000_000
    base = dict(max=31.0, cur=29.5, cur_ts=now_ts - 600, first_ts=now_ts - 12 * 3600, n=20)
    bucket = {"label": "31°C", "token_yes": "x", "accepting": True}
    common = dict(now_ts=now_ts, coverage_deadline_ts=now_ts - 8 * 3600, source="metar",
                  bucket=bucket, top=bucket, accepting=True, ask=0.97, spent_today=0, halt=False)
    ok, _, r = decide.check_guards(stats=base, **common)
    check("护栏: 正常情况放行", ok, r)
    ok, _, r = decide.check_guards(stats=dict(base, cur=30.5), **common)
    check("护栏: 降温不足拦截", not ok, r)
    ok, _, r = decide.check_guards(stats=base, **{**common, "ask": 0.9985})
    check("护栏: 价太高拦截", not ok, r)
    ok, _, r = decide.check_guards(stats=base, **{**common, "ask": 0.85})
    check("护栏: 价太低拦截", not ok, r)
    ok, _, r = decide.check_guards(stats=base, **{**common, "top": {"label": "32°C"}})
    check("护栏: 市场共识不一致拦截", not ok, r)
    ok, _, r = decide.check_guards(stats=base, **{**common, "halt": True})
    check("护栏: 紧急停止拦截", not ok, r)
    ok, _, r = decide.check_guards(stats=base, **{**common, "spent_today": 28})
    check("护栏: 日上限拦截", not ok, r)
    ok, _, r = decide.check_guards(stats=dict(base, first_ts=now_ts - 3600), **common)
    check("护栏: 覆盖不全拦截", not ok, r)
    ok, _, r = decide.check_guards(stats=dict(base, cur_ts=now_ts - 7200), **common)
    check("护栏: 数据过旧拦截", not ok, r)
    check("HK floor: 33.5→33", decide.bucket_int_for("hko", 33.5) == 33)
    check("HK floor: 31.9→31", decide.bucket_int_for("hko", 31.9) == 31)
    check("METAR: 31→31", decide.bucket_int_for("metar", 31.0) == 31)


def t_hk_rule():
    """全月实证: HKO 官方日最高 (Daily Extract, 结算源) vs 已结算市场赢家 → floor 必须全对."""
    now = datetime.now(TZ)
    ym = f"{now.year}{now.month:02d}"
    url = f"https://www.hko.gov.hk/cis/dailyExtract/dailyExtract_{ym}.xml"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = json.load(urllib.request.urlopen(req, timeout=20))
    days = raw["stn"]["data"][0]["dayData"]
    n_checked = n_ok = 0
    for row in days:
        try:
            day = int(row[0])
            official = float(row[2])  # col2 = 日最高气温
        except (ValueError, IndexError):
            continue
        d = datetime(now.year, now.month, day, tzinfo=TZ).date()
        if d >= now.date():
            continue
        try:
            ev = markets.fetch_event(markets.event_slug("hong-kong", d))
        except Exception:
            continue
        if not ev or not ev["closed"]:
            continue
        win = markets.winning_bucket(ev["buckets"])
        if not win:
            continue
        n_checked += 1
        expect = markets.pick_bucket(ev["buckets"], decide.bucket_int_for("hko", official))
        if expect and expect["label"] == win["label"]:
            n_ok += 1
        else:
            print(f"   ⚠️ {d}: 官方 {official}° → 我们算 {expect and expect['label']}, "
                  f"实际赢家 {win['label']}")
    check("香港 floor 规则全月回测", n_checked > 0 and n_ok == n_checked,
          f"{n_ok}/{n_checked} 天全对")


if __name__ == "__main__":
    print("=== 天气 bot 自检 (绝不下单) ===")
    for fn in (t_sunset, t_market, t_wx, t_guards, t_hk_rule):
        try:
            fn()
        except Exception as e:
            check(fn.__name__, False, f"异常: {e}")
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n=== {len(RESULTS) - len(bad)}/{len(RESULTS)} 通过 ===")
    sys.exit(1 if bad else 0)
