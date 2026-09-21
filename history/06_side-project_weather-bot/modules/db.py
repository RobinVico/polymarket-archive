"""SQLite 存储 (weather.db, WAL 模式). 表: obs 气温观测 / plans 每日每城计划 / kv 杂项."""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "weather.db")
_lock = threading.Lock()


def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    with _lock, get_conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS obs(
            city TEXT NOT NULL,
            ts   INTEGER NOT NULL,
            temp REAL NOT NULL,
            PRIMARY KEY(city, ts))""")
        c.execute("""CREATE TABLE IF NOT EXISTS plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_date TEXT NOT NULL,
            city TEXT NOT NULL,
            event_slug TEXT DEFAULT '',
            event_title TEXT DEFAULT '',
            sunset_utc TEXT DEFAULT '',
            fire_utc TEXT DEFAULT '',
            deadline_utc TEXT DEFAULT '',
            end_date_utc TEXT DEFAULT '',
            status TEXT DEFAULT 'watching',
            day_max REAL,
            cur_temp REAL,
            bucket INTEGER,
            bucket_label TEXT DEFAULT '',
            token_id TEXT DEFAULT '',
            best_ask REAL,
            order_usd REAL DEFAULT 0,
            filled_shares REAL DEFAULT 0,
            filled_usd REAL DEFAULT 0,
            mode TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            attempts INTEGER DEFAULT 0,
            breached INTEGER DEFAULT 0,
            decided_at TEXT DEFAULT '',
            resolved_at TEXT DEFAULT '',
            winning_label TEXT DEFAULT '',
            pnl REAL,
            created_at TEXT DEFAULT '',
            UNIQUE(local_date, city))""")
        c.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")


# ===== obs =====

def save_obs(city, ts, temp):
    with _lock, get_conn() as c:
        c.execute("INSERT OR IGNORE INTO obs(city, ts, temp) VALUES(?,?,?)",
                  (city, int(ts), float(temp)))


def day_obs_stats(city, start_ts, end_ts):
    """[start_ts, end_ts) 区间的观测统计. 无数据返回 None."""
    with get_conn() as c:
        rows = c.execute(
            "SELECT ts, temp FROM obs WHERE city=? AND ts>=? AND ts<? ORDER BY ts",
            (city, int(start_ts), int(end_ts))).fetchall()
    if not rows:
        return None
    temps = [r["temp"] for r in rows]
    return {
        "max": max(temps),
        "n": len(rows),
        "cur": rows[-1]["temp"],
        "cur_ts": rows[-1]["ts"],
        "first_ts": rows[0]["ts"],
    }


# ===== plans =====

_PLAN_FIELDS = {
    "event_slug", "event_title", "sunset_utc", "fire_utc", "deadline_utc", "end_date_utc",
    "status", "day_max", "cur_temp", "bucket", "bucket_label", "token_id", "best_ask",
    "order_usd", "filled_shares", "filled_usd", "mode", "reason", "attempts", "breached",
    "decided_at", "resolved_at", "winning_label", "pnl",
}


def create_plan(local_date, city, **fields):
    cols = ["local_date", "city", "created_at"]
    vals = [local_date, city, utcnow_iso()]
    for k, v in fields.items():
        if k in _PLAN_FIELDS:
            cols.append(k)
            vals.append(v)
    with _lock, get_conn() as c:
        c.execute(
            f"INSERT OR IGNORE INTO plans({','.join(cols)}) VALUES({','.join('?' * len(vals))})",
            vals)


def get_plan(local_date, city):
    with get_conn() as c:
        r = c.execute("SELECT * FROM plans WHERE local_date=? AND city=?",
                      (local_date, city)).fetchone()
    return dict(r) if r else None


def update_plan(plan_id, **fields):
    sets, vals = [], []
    for k, v in fields.items():
        if k in _PLAN_FIELDS:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(plan_id)
    with _lock, get_conn() as c:
        c.execute(f"UPDATE plans SET {','.join(sets)} WHERE id=?", vals)


def plans_for_date(local_date):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM plans WHERE local_date=? ORDER BY fire_utc",
                         (local_date,)).fetchall()
    return [dict(r) for r in rows]


def watching_plans():
    with get_conn() as c:
        rows = c.execute("SELECT * FROM plans WHERE status='watching'").fetchall()
    return [dict(r) for r in rows]


def pending_resolution():
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM plans WHERE status IN ('ordered','would_buy')").fetchall()
    return [dict(r) for r in rows]


def recent_plans(limit=40):
    with get_conn() as c:
        rows = c.execute("SELECT * FROM plans ORDER BY local_date DESC, id DESC LIMIT ?",
                         (limit,)).fetchall()
    return [dict(r) for r in rows]


def spent_on_date(local_date):
    """当日已占用额度 = 真买 + would_buy (待钱包/PAPER 也占额度, 保证行为前后一致)."""
    with get_conn() as c:
        r = c.execute(
            "SELECT COALESCE(SUM(order_usd),0) s FROM plans "
            "WHERE local_date=? AND status IN ('ordered','would_buy','won','lost')",
            (local_date,)).fetchone()
    return float(r["s"] or 0)


def stats_summary():
    """历史成绩: 真钱/模拟分开算."""
    out = {"real_pnl": 0.0, "paper_pnl": 0.0, "won": 0, "lost": 0, "n_resolved": 0}
    with get_conn() as c:
        rows = c.execute(
            "SELECT status, mode, pnl FROM plans WHERE status IN ('won','lost')").fetchall()
    for r in rows:
        out["n_resolved"] += 1
        if r["status"] == "won":
            out["won"] += 1
        else:
            out["lost"] += 1
        if r["pnl"] is not None:
            if r["mode"] == "real":
                out["real_pnl"] += r["pnl"]
            else:
                out["paper_pnl"] += r["pnl"]
    out["hit_rate"] = (out["won"] / out["n_resolved"] * 100) if out["n_resolved"] else None
    return out


# ===== kv =====

def kv_get(k, default=None):
    with get_conn() as c:
        r = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def kv_set(k, v):
    with _lock, get_conn() as c:
        c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                  (k, str(v)))


def add_alert(msg):
    """dashboard 红条提醒 (最多留 20 条)."""
    try:
        alerts = json.loads(kv_get("alerts", "[]"))
    except Exception:
        alerts = []
    alerts.append({"ts": utcnow_iso(), "msg": msg})
    kv_set("alerts", json.dumps(alerts[-20:], ensure_ascii=False))


def get_alerts():
    try:
        return json.loads(kv_get("alerts", "[]"))
    except Exception:
        return []


def clear_alerts():
    kv_set("alerts", "[]")
