import sqlite3
from datetime import datetime, timedelta

DB_PATH = "trading_bot.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            market_slug TEXT,
            detail TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_spend (
            date TEXT PRIMARY KEY,
            total_usd REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            market_slug TEXT NOT NULL,
            side TEXT NOT NULL,
            action TEXT NOT NULL,
            amount_usd REAL,
            price REAL,
            confidence TEXT,
            true_prob REAL,
            settle_date TEXT,
            reasoning TEXT,
            claude_report TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY,
            pnl REAL DEFAULT 0,
            trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            spent REAL DEFAULT 0,
            phase TEXT DEFAULT 'phase1'
        );
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        INSERT OR IGNORE INTO config (key, value) VALUES ('phase', 'phase1');
    """)
    conn.commit()
    conn.close()

def log_event(event_type, market_slug, detail=""):
    conn = get_conn()
    conn.execute("INSERT INTO events (timestamp, event_type, market_slug, detail) VALUES (?,?,?,?)",
                 (datetime.now().isoformat(), event_type, market_slug, detail))
    conn.commit(); conn.close()

def get_daily_spend(date_str=None):
    if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    row = conn.execute("SELECT total_usd FROM daily_spend WHERE date=?", (date_str,)).fetchone()
    conn.close()
    return row["total_usd"] if row else 0.0

def add_daily_spend(amount, date_str=None):
    if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    conn.execute("INSERT INTO daily_spend (date, total_usd) VALUES (?,?) ON CONFLICT(date) DO UPDATE SET total_usd=total_usd+?",
                 (date_str, amount, amount))
    conn.commit(); conn.close()

def get_recent_events(limit=50):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_trade(market_slug, side, action, amount, price, confidence, true_prob, settle_date, reasoning, report):
    conn = get_conn()
    conn.execute(
        "INSERT INTO trades (timestamp,market_slug,side,action,amount_usd,price,confidence,true_prob,settle_date,reasoning,claude_report) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (datetime.now().isoformat(), market_slug, side, action, amount, price, confidence, true_prob, settle_date, reasoning, report[:2000] if report else ""))
    conn.commit(); conn.close()

def get_current_phase():
    conn = get_conn()
    row = conn.execute("SELECT value FROM config WHERE key='phase'").fetchone()
    conn.close()
    return row["value"] if row else "phase1"

def set_phase(phase):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO config (key,value) VALUES ('phase',?)", (phase,))
    conn.commit(); conn.close()

def get_stats(days=30):
    conn = get_conn()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("SELECT * FROM daily_stats WHERE date >= ?", (since,)).fetchall()
    conn.close()
    if not rows: return None
    total_pnl = sum(r["pnl"] for r in rows)
    total_trades = sum(r["trades"] for r in rows)
    total_wins = sum(r["wins"] for r in rows)
    win_rate = total_wins / total_trades if total_trades > 0 else 0
    return {"days": len(rows), "trades": total_trades, "total_pnl": total_pnl,
            "win_rate": win_rate, "max_drawdown": 0, "consec_loss_days": 0}
