"""Polymarket 天气市场发现 + 档位解析 + 公开盘口.

事件 slug 规律: highest-temperature-in-{city}-on-{july-12}-{2026}
每个事件 = negRisk 多档, 每档一个二元市场, question 形如:
  "Will the highest temperature in Shanghai be 25°C or below on July 12?"
  "Will the highest temperature in Shanghai be 31°C on July 12?"
  "Will the highest temperature in Shanghai be 35°C or higher on July 12?"
"""
import json
import logging
import re
from datetime import datetime, timezone

import requests

from modules.gamma_client import gamma_get, GammaError

log = logging.getLogger("markets")

MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]

_BUCKET_RE = re.compile(r"be (\d+)\s*°C( or below| or higher)?", re.I)
_UA = {"User-Agent": "tianqi-bot/0.1"}


def event_slug(slug_city, local_date):
    return (f"highest-temperature-in-{slug_city}-on-"
            f"{MONTHS[local_date.month - 1]}-{local_date.day}-{local_date.year}")


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def fetch_event(slug):
    """拉事件 + 解析全部档位. 找不到返回 None; 网络失败抛 GammaError."""
    evs = gamma_get("/events", {"slug": slug}, timeout=15)
    if not evs:
        return None
    ev = evs[0] if isinstance(evs, list) else evs
    buckets = []
    for m in ev.get("markets", []):
        q = m.get("question") or ""
        mm = _BUCKET_RE.search(q)
        if not mm:
            continue
        n = int(mm.group(1))
        suffix = (mm.group(2) or "").strip()
        if suffix == "or below":
            lo, hi, label = None, n, f"≤{n}°C"
        elif suffix == "or higher":
            lo, hi, label = n, None, f"≥{n}°C"
        else:
            lo, hi, label = n, n, f"{n}°C"
        try:
            toks = json.loads(m.get("clobTokenIds") or "[]")
        except Exception:
            toks = []
        try:
            prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
        except Exception:
            prices = []
        try:
            outcomes = json.loads(m.get("outcomes") or '["Yes","No"]')
        except Exception:
            outcomes = ["Yes", "No"]
        yes_idx = 0 if (outcomes and str(outcomes[0]).lower() == "yes") else 1
        buckets.append({
            "label": label, "lo": lo, "hi": hi, "question": q,
            "token_yes": toks[yes_idx] if len(toks) > yes_idx else None,
            "yes_price": prices[yes_idx] if len(prices) > yes_idx else None,
            "accepting": bool(m.get("acceptingOrders")),
            "closed": bool(m.get("closed")),
        })
    buckets.sort(key=lambda b: (b["lo"] if b["lo"] is not None else -999))
    return {
        "slug": slug,
        "title": ev.get("title") or "",
        "closed": bool(ev.get("closed")),
        "end_date": _parse_iso(ev.get("endDate")),
        "buckets": buckets,
    }


def pick_bucket(buckets, t_int):
    """整数温度落进哪个档."""
    for b in buckets:
        lo = b["lo"] if b["lo"] is not None else -10**6
        hi = b["hi"] if b["hi"] is not None else 10**6
        if lo <= t_int <= hi:
            return b
    return None


def top_bucket(buckets):
    """市场当前最贵 (共识) 的档."""
    live = [b for b in buckets if b.get("yes_price") is not None]
    return max(live, key=lambda b: b["yes_price"]) if live else None


def winning_bucket(buckets):
    """已结算事件里 YES≈1 的档."""
    for b in buckets:
        if (b.get("yes_price") or 0) > 0.95:
            return b
    return None


def best_ask_public(token_id):
    """CLOB 公开盘口卖一价 (无需鉴权; 钱包没配也能用). 失败返回 None."""
    try:
        r = requests.get("https://clob.polymarket.com/book",
                         params={"token_id": token_id}, timeout=10, headers=_UA)
        r.raise_for_status()
        asks = (r.json() or {}).get("asks") or []
        prices = [float(a.get("price")) for a in asks if a.get("price")]
        return min(prices) if prices else None
    except Exception as e:
        log.warning(f"best_ask_public 失败 {str(token_id)[:16]}: {e}")
        return None
