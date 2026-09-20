"""三号账户 (shadow · 低价拿到底): 把 GLM「测试仓那半」推荐 (≤$0.40) 在独立新账户【真买】。

用户 2026-07-24 拍板的死规则 (同一套 GLM 推荐, 三账户三策略的第三种; 前两种=主策略+bench):
  1. 只吃 auto_candidates 里 status='paper' 的候选 —— 'paper:黑名单强制' 天然不匹配 = 黑名单永不真买;
     宇宙闸门/白名单主链路早就把过关, 天然继承。≥0.85 那半被下面的价格线挡住 = 永远排除。
  2. 临下单拉新鲜 ask, **≤ 0.40 才买** (SHADOW_MAX_PRICE); 漂出去点名跳过。
  3. 每仓固定 **$2** (SHADOW_USD_PER_POS), 赔率型广撒网等权。
  4. **止损不止盈**: 入场锚 −60% (SHADOW_STOP_PCT) + $0.05 地板 (SHADOW_FLOOR), 连 3 拍确认防瞬时假价。
     无止盈 / 无重评 / 无时间止损 / 无移动止损 —— 涨就拿到结算。
     (止损值依据 2026-07-24 回撤研究: 18 条低价仓历史路径 — 唯一真赢家(胡塞0.38→$1)中途最深跌 −55%,
      输家全部奔零 → −60% 放得过赢家、把死仓从 −85%~−100% 救回 −60%; −50% 会杀掉那个赢家, 数据反对。)
  5. **只买启用之后的新推荐** (存量测试仓不补买): start_at 标记首次激活时落库; dry→真钱切换时重置。

凭据 (.env, 用户自己填; 命名跟 bench 的 BENCH_POLY_* 同一套约定):
  SHADOW_POLY_PRIVATE_KEY / SHADOW_POLY_FUNDER / SHADOW_POLY_SIGNATURE_TYPE (存款钱包默认 3)。
  没配 → 待命 (只注册只读路由, 零操作)。SHADOW_ENABLED=0 整体关闭。
  SHADOW_DRY_RUN=1 = 空跑 (不构造下单实例、不花钱, 假成交按新鲜 ask 记, 行打 dry=1) — 上真钱前 E2E 用。

双账户隔离 (照抄 auto_bench 已验证的安全设计, 一条不能少):
  - 绝不碰 Executor.get() 单例; env 临时换 SHADOW_POLY_* 直接构造第二个 Executor 实例
    (必须在 autobot 主线程、app.run 之前), finally 原样恢复。buy()/sell() 走 self.client 实例安全,
    整数股/negRisk/tick 的 sig=3 老坑全复用。
  - 绝不用 exe.get_positions() (读模块级 FUNDER=主账户) / exe.get_cash_balance() (写 Executor._live_cash
    类缓存 → 三号现金会漏进主页面) — 本模块自带 _positions()/_cash()。
  - 同凭据误配守卫: SHADOW 凭据 == 主账户 或 == bench → 拒绝启动 (防在别的账户上乱下单乱止损)。
  - 主 monitor/重评/bench 都看不见三号仓 (各查各的 funder) — 零互相干扰。
"""
import os
import re
import time
import logging
import threading
from datetime import datetime, timezone

import requests as rq

log = logging.getLogger("auto_shadow")

DATA_API = "https://data-api.polymarket.com"

ENABLED = os.environ.get("SHADOW_ENABLED", "1") not in ("0", "false", "False", "")
DRY_RUN = os.environ.get("SHADOW_DRY_RUN", "0") in ("1", "true", "True")
_funder = (os.environ.get("SHADOW_POLY_FUNDER") or "").strip()
MAX_PRICE = float(os.environ.get("SHADOW_MAX_PRICE", "0.40"))
STAKE_USD = float(os.environ.get("SHADOW_USD_PER_POS", "2"))
STOP_PCT = float(os.environ.get("SHADOW_STOP_PCT", "0.60"))
FLOOR = float(os.environ.get("SHADOW_FLOOR", "0.05"))
POLL_S = float(os.environ.get("SHADOW_POLL_S", "30"))
CONFIRM_ROUNDS = int(os.environ.get("SHADOW_CONFIRM_ROUNDS", "3"))
CAND_TTL_H = float(os.environ.get("SHADOW_CANDIDATE_TTL_H", "24"))

_exe = None                    # 三号账户 Executor 实例 (env 交换法, 只构造一次; DRY 模式恒 None)
_thread_started = False
_breach = {}                   # token_id -> 连续跌破止损线拍数 (内存)
_pos_cache = (0.0, None)       # (ts, list) 三号钱包仓位 35s 缓存
_last_cash_warn = 0.0          # 现金不足告警节流 (10min 一次)


def is_configured():
    if DRY_RUN:
        return True
    return bool((os.environ.get("SHADOW_POLY_PRIVATE_KEY") or "").strip()) and bool(_funder)


# ---------- DB (自建表, 不动 db.py) ----------

def _ensure_tables():
    from modules.db import get_conn
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS shadow_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cand_id INTEGER, token_id TEXT, market_slug TEXT,
        title TEXT, side TEXT, entry_price REAL, shares REAL, stake_usd REAL, stop_price REAL,
        created_at TEXT, status TEXT DEFAULT 'pending', exit_price REAL, exit_reason TEXT,
        exit_at TEXT, final_outcome REAL, realized_pnl_usd REAL, dry INTEGER DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS shadow_done (
        cand_id INTEGER PRIMARY KEY, ts TEXT, result TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS shadow_state (
        key TEXT PRIMARY KEY, value TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS shadow_snapshot (
        ts INTEGER, cash REAL, pos_value REAL, pos_cost REAL, total REAL)""")
    conn.commit()
    conn.close()


def _db_rows(sql, args=()):
    from modules.db import get_conn
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return rows


def _db_exec(sql, args=()):
    from modules.db import get_conn
    conn = get_conn()
    conn.execute(sql, args)
    conn.commit()
    conn.close()


def _state_get(key, default=None):
    rows = _db_rows("SELECT value FROM shadow_state WHERE key=?", (key,))
    return rows[0]["value"] if rows else default


def _state_set(key, value):
    _db_exec("INSERT OR REPLACE INTO shadow_state (key, value) VALUES (?,?)", (key, value))


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _mark_done(cand_id, result):
    _db_exec("INSERT OR REPLACE INTO shadow_done (cand_id, ts, result) VALUES (?,?,?)",
             (cand_id, _utcnow(), str(result)[:200]))


# ---------- 三号账户通道 (隔离铁三样: 自建 executor / 自查仓 / 自查现金) ----------

def _make_executor():
    """env 交换法构造三号 Executor 实例 (不碰 .get() 单例)。只在 autobot 主线程启动时调一次。"""
    from modules.executor import Executor
    key = (os.environ.get("SHADOW_POLY_PRIVATE_KEY") or "").strip()
    sig = (os.environ.get("SHADOW_POLY_SIGNATURE_TYPE") or "3").strip()
    saved = {k: os.environ.get(k) for k in ("POLY_PRIVATE_KEY", "POLY_FUNDER", "POLY_SIGNATURE_TYPE")}
    try:
        os.environ["POLY_PRIVATE_KEY"] = key
        os.environ["POLY_FUNDER"] = _funder
        os.environ["POLY_SIGNATURE_TYPE"] = sig
        return Executor()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _positions(fresh=False):
    """三号账户实时仓位 (data-api 直查 SHADOW funder, 35s 缓存)。
    ⚠️ 出错返回 None (跟 executor 的"出错返回[]"故意不同 — [] 会被误读成仓全没了)。DRY 模式恒 None。"""
    global _pos_cache
    if DRY_RUN:
        return None
    if not fresh and _pos_cache[1] is not None and time.time() - _pos_cache[0] < 35:
        return _pos_cache[1]
    try:
        raw = rq.get(f"{DATA_API}/positions",
                     params={"user": _funder, "limit": 200, "sizeThreshold": 0}, timeout=15).json()
        out = []
        for p in (raw if isinstance(raw, list) else []):
            sz = float(p.get("size") or 0)
            if sz <= 0:
                continue
            out.append({"asset": p.get("asset"), "size": sz,
                        "avg_price": float(p.get("avgPrice") or 0),
                        "cur_price": float(p.get("curPrice") or 0),
                        "title": p.get("title") or ""})
        _pos_cache = (time.time(), out)
        return out
    except Exception as e:
        log.warning(f"[shadow] 查仓失败: {e}")
        return None


def _cash():
    """三号账户现金 (走三号 client; 绝不写 Executor._live_cash 类缓存)。失败/DRY 返回 None。"""
    if DRY_RUN or _exe is None:
        return None
    try:
        from py_clob_client_v2 import BalanceAllowanceParams, AssetType
        r = _exe.client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        bal = r.get("balance") if isinstance(r, dict) else getattr(r, "balance", None)
        return float(bal) / 1_000_000 if bal is not None else None
    except Exception as e:
        log.warning(f"[shadow] 现金查询失败: {e}")
        return None


# ---------- 买入: 吃 paper 候选 ----------

def _open_tokens():
    return {r["token_id"] for r in _db_rows(
        "SELECT token_id FROM shadow_positions WHERE status IN ('pending','open')")}


def _consume_candidates():
    """吃主链路标成 'paper' 的候选 (只吃 start_at 之后的), 新鲜 ask ≤ MAX_PRICE 才买 $2。
    崩溃安全: 先插 pending 行再下单, 成交后置 open (卡死的 pending 由 _recover_pending 收拾)。"""
    from modules.db import log_event
    from modules.auto_trader import _resolve_token, _fresh_ask
    start_at = _state_get("start_at")
    if not start_at:
        return
    rows = _db_rows("SELECT * FROM auto_candidates WHERE status='paper' AND created_at > ? "
                    "AND id NOT IN (SELECT cand_id FROM shadow_done) ORDER BY id LIMIT 20", (start_at,))
    for row in rows:
        cid = row["id"]
        slug = (row.get("slug") or "").strip()
        side = (row.get("side") or "").strip().upper()
        label = f"{(row.get('title') or slug)[:40]} {side}"
        try:
            try:
                age_h = (datetime.now(timezone.utc)
                         - datetime.fromisoformat(str(row.get("created_at")).replace("Z", "+00:00"))
                         ).total_seconds() / 3600
            except Exception:
                age_h = 0
            if age_h > CAND_TTL_H:
                _mark_done(cid, f"skip:过期{age_h:.0f}h")
                continue
            # 宇宙闸门复查 (07-08 体育误买铁律): 不信任 status='paper' 的来源, 真买前自己再验一遍
            # tag∈白名单 + slug 在扫描报告里; 带黑名单标记的也拒 (黑名单永不真买)。防合成行/幻觉 slug。
            from modules.auto_trader import _in_universe
            ok_u, why_u, blacklisted = _in_universe(row)
            if not ok_u or blacklisted:
                _mark_done(cid, f"skip:宇宙闸{'(黑名单)' if blacklisted else ''}:{why_u}"[:120])
                log.warning(f"[shadow] ⛔ 宇宙闸拒 {label}: {why_u} blacklisted={blacklisted}")
                continue
            token, closed, _all = _resolve_token(slug, side)
            if not token or closed:
                _mark_done(cid, "skip:市场关闭或查不到token")
                continue
            if token in _open_tokens():
                _mark_done(cid, "skip:已持有该token")
                continue
            ask = _fresh_ask(token)
            if not ask or not (0 < ask < 1):
                _mark_done(cid, "skip:无盘口")
                continue
            if ask > MAX_PRICE:
                _mark_done(cid, f"skip:新鲜价{ask:.3f}>上限{MAX_PRICE:g}")
                continue
            if DRY_RUN:
                shares = round(STAKE_USD / ask, 2)
                _db_exec("""INSERT INTO shadow_positions (cand_id, token_id, market_slug, title, side,
                    entry_price, shares, stake_usd, stop_price, created_at, status, dry)
                    VALUES (?,?,?,?,?,?,?,?,?,?,'open',1)""",
                    (cid, token, slug, row.get("title") or slug, side, ask, shares, STAKE_USD,
                     round(ask * (1 - STOP_PCT), 4), _utcnow()))
                _mark_done(cid, f"dry-bought:@{ask:.3f}")
                log.info(f"[shadow] 🧪(dry) 假买 {label}: {shares}股 @ {ask:.3f}")
                continue
            cash = _cash()
            if cash is None or cash < STAKE_USD:
                # 不标 done — 候选留着, 24h 保鲜期内每轮重试; 用户充值到账后自动补上车 (2026-07-24)
                global _last_cash_warn
                if time.time() - _last_cash_warn > 600:
                    _last_cash_warn = time.time()
                    log.warning(f"[shadow] 现金不足(${cash}), 候选暂缓不作废 (充值到账即自动买): {label} 等 {len(rows)} 条")
                break
            # 先落 pending 行 (崩溃安全), 再真下单
            _db_exec("""INSERT INTO shadow_positions (cand_id, token_id, market_slug, title, side,
                stake_usd, stop_price, created_at, status) VALUES (?,?,?,?,?,?,?,?, 'pending')""",
                (cid, token, slug, row.get("title") or slug, side, STAKE_USD,
                 round(ask * (1 - STOP_PCT), 4), _utcnow()))
            _mark_done(cid, "pending")
            ok, msg = _exe.buy(token, STAKE_USD, reason="shadow_longshot")
            msg = str(msg or "")
            if not ok:
                _db_exec("UPDATE shadow_positions SET status=? WHERE cand_id=?",
                         (("error:buy:" + msg)[:120], cid))
                _mark_done(cid, "error:buy:" + msg[:80])
                log.warning(f"[shadow] 买入失败 {label}: {msg}")
                continue
            m_sh = re.search(r"([0-9.]+)\s*股", msg)
            m_usd = re.search(r"≈ \$([0-9.]+)", msg)
            m_px = re.search(r"@ ([0-9.]+)%", msg)
            shares = float(m_sh.group(1)) if m_sh else round(STAKE_USD / ask, 2)
            usd_act = float(m_usd.group(1)) if m_usd else STAKE_USD
            entry = (float(m_px.group(1)) / 100.0) if m_px else ask
            _db_exec("""UPDATE shadow_positions SET status='open', entry_price=?, shares=?, stake_usd=?,
                stop_price=? WHERE cand_id=?""",
                (entry, shares, usd_act, round(entry * (1 - STOP_PCT), 4), cid))
            _mark_done(cid, f"bought:${usd_act:.2f}@{entry:.3f}")
            log_event("shadow_buy", row.get("title") or slug,
                      f"三号账户买入 ${usd_act:.2f} {side} @ ~{entry:.3f} (止损线 {entry*(1-STOP_PCT):.3f}, 拿到结算)")
            log.info(f"[shadow] 🟣 已买 {label}: {shares}股 @ {entry:.3f} ≈ ${usd_act:.2f}")
        except Exception as e:
            log.exception(f"[shadow] 处理候选 {cid} 异常: {e}")
            _mark_done(cid, f"error:{e}")


def _recover_pending():
    """启动/巡逻时收拾卡死的 pending (下单后进程崩了没记账): 钱包里看到了 → 补 open; 看不到 → 标 error。"""
    rows = _db_rows("SELECT * FROM shadow_positions WHERE status='pending'")
    if not rows:
        return
    wallet = _positions(fresh=True)
    for r in rows:
        try:
            age_min = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(str(r["created_at"]))).total_seconds() / 60
        except Exception:
            age_min = 99
        if age_min < 5:
            continue
        w = next((p for p in (wallet or []) if p["asset"] == r["token_id"]), None)
        if w:
            entry = w["avg_price"] or 0
            _db_exec("UPDATE shadow_positions SET status='open', entry_price=?, shares=?, stop_price=? WHERE id=?",
                     (entry, w["size"], round(entry * (1 - STOP_PCT), 4) if entry else None, r["id"]))
            log.info(f"[shadow] 恢复 pending→open: {r['title'][:30]}")
        elif wallet is not None:
            _db_exec("UPDATE shadow_positions SET status='error:pending-unknown' WHERE id=?", (r["id"],))


# ---------- 止损 (唯一的卖出规则) ----------

def _check_stops():
    """现价 ≤ 入场−60% 线 或 < $0.05 地板, 连 CONFIRM_ROUNDS 拍确认 → 全卖。无止盈/无重评。"""
    from modules.db import log_event
    open_rows = _db_rows("SELECT * FROM shadow_positions WHERE status='open'")
    if not open_rows:
        return
    wallet = None
    if not DRY_RUN:
        wallet = _positions()
        if wallet is None:
            return   # 查仓失败这拍不动 (防把 API 故障当归零)
    for pos in open_rows:
        tok = pos["token_id"]
        if DRY_RUN:
            from modules.auto_trader import _fresh_ask
            cur = _fresh_ask(tok)
            size = pos["shares"]
        else:
            w = next((p for p in wallet if p["asset"] == tok), None)
            if not w:
                continue   # 钱包暂时没看到 (同步延迟/已赎回) — 结算判定另有低频检查
            cur, size = w.get("cur_price"), w.get("size")
        if not cur or cur <= 0:
            continue
        breach_floor = cur < FLOOR
        breach_stop = pos["stop_price"] is not None and cur <= pos["stop_price"]
        if not (breach_floor or breach_stop):
            _breach.pop(tok, None)
            continue
        n = _breach.get(tok, 0) + 1
        _breach[tok] = n
        if n < CONFIRM_ROUNDS:
            continue
        _breach.pop(tok, None)
        why = f"跌破${FLOOR:.2f}地板" if breach_floor else f"入场锚-{int(STOP_PCT*100)}%止损"
        if DRY_RUN:
            ok = True
        else:
            res = _exe.sell(tok, size, reason=f"shadow_stop:{why}")
            ok = res[0] if isinstance(res, tuple) else bool(res)
            if not ok:
                log.warning(f"[shadow] 止损卖出失败 {pos['title'][:30]}: {res}")
                continue
        pnl = round(cur * (size or 0) - (pos["stake_usd"] or 0), 2)
        _db_exec("UPDATE shadow_positions SET status='stopped', exit_price=?, exit_reason=?, exit_at=?, "
                 "realized_pnl_usd=? WHERE id=?", (cur, why, _utcnow(), pnl, pos["id"]))
        log_event("shadow_sell", pos["title"] or pos["market_slug"],
                  f"三号账户止损 {why} @ ~{cur:.3f} pnl≈{pnl:+.2f}" + (" (dry)" if DRY_RUN else ""))
        log.info(f"[shadow] 🔻 止损 {pos['title'][:36]} @ {cur:.3f} ({why}, pnl≈{pnl:+.2f})")


# ---------- 结算 (低频) ----------

def _check_resolutions():
    from modules.db import log_event
    for pos in _db_rows("SELECT * FROM shadow_positions WHERE status='open'"):
        try:
            g = rq.get("https://gamma-api.polymarket.com/markets",
                       params={"slug": pos["market_slug"], "limit": 1, "closed": "true"}, timeout=10).json()
            if not (g and isinstance(g, list)):
                continue
            # 结算了: 赢输按我方 token 末价判 (>0.5 = 我方兑现)
            from modules.auto_trader import _fresh_ask
            wallet = _positions(fresh=True)
            w = next((p for p in (wallet or []) if p["asset"] == pos["token_id"]), None)
            last = (w.get("cur_price") if w else None) or _fresh_ask(pos["token_id"]) or 0
            won = 1.0 if last > 0.5 else 0.0
            pnl = round((pos["shares"] or 0) * (1.0 if won else 0.0) - (pos["stake_usd"] or 0), 2)
            _db_exec("UPDATE shadow_positions SET status='resolved', final_outcome=?, exit_price=?, "
                     "exit_reason='结算', exit_at=?, realized_pnl_usd=? WHERE id=?",
                     (won, 1.0 if won else 0.0, _utcnow(), pnl, pos["id"]))
            log_event("shadow_resolve", pos["title"] or pos["market_slug"],
                      f"三号账户结算 {'赢→$1' if won else '输→$0'} pnl≈{pnl:+.2f}" + (" (dry)" if pos.get("dry") else ""))
            log.info(f"[shadow] 🏁 结算 {pos['title'][:36]}: {'赢' if won else '输'} pnl≈{pnl:+.2f}")
        except Exception as e:
            log.warning(f"[shadow] 结算检查失败 {pos['market_slug']}: {e}")


def _write_snapshot():
    """资产快照 (每~10min): /shadow 页资产曲线数据源 (schema 对齐 bench_snapshot)。API 失败这拍不写。"""
    if DRY_RUN:
        return
    wallet = _positions(fresh=True)
    cash = _cash()
    if wallet is None or cash is None:
        return
    pos_value = sum((p.get("cur_price") or 0) * (p.get("size") or 0) for p in wallet)
    rows = _db_rows("SELECT COALESCE(SUM(stake_usd),0) c FROM shadow_positions WHERE status='open'")
    pos_cost = rows[0]["c"] or 0
    _db_exec("INSERT INTO shadow_snapshot (ts, cash, pos_value, pos_cost, total) VALUES (?,?,?,?,?)",
             (int(time.time()), cash, pos_value, pos_cost, pos_value + cash))


# ---------- 主循环 / 启动 / 路由 ----------

def _loop():
    tick = 0
    log.info(f"[shadow] 三号账户巡逻启动{'(DRY空跑)' if DRY_RUN else ''}: 每{POLL_S:g}s | 只买≤{MAX_PRICE:g} | "
             f"${STAKE_USD:g}/仓 | 止损 入场-{int(STOP_PCT*100)}% + ${FLOOR:.2f}地板 (连{CONFIRM_ROUNDS}拍) | "
             f"不止盈/不重评, 拿到结算")
    while True:
        try:
            _state_set("last_tick", _utcnow())   # 心跳: 活性证明 (状态页/巡检用; "没动静"≠"死了")
            _consume_candidates()
            _check_stops()
            if tick % 10 == 5:
                _recover_pending()
            if tick % 20 == 0:
                _check_resolutions()
                _write_snapshot()
        except Exception as e:
            log.exception(f"[shadow] loop异常: {e}")
        tick += 1
        time.sleep(POLL_S)


def start_shadow():
    """autobot 主线程、app.run 之前调用。没配凭据 = 待命。"""
    global _exe, _thread_started
    if not ENABLED:
        log.info("[shadow] SHADOW_ENABLED=0, 三号账户关闭")
        return
    if not is_configured():
        log.info("[shadow] 三号账户待命: .env 未配 SHADOW_POLY_PRIVATE_KEY / SHADOW_POLY_FUNDER "
                 "(配好重启即自动激活; SHADOW_DRY_RUN=1 可先空跑)")
        return
    if _thread_started:
        return
    _ensure_tables()
    mode = "dry" if DRY_RUN else "real"
    if not DRY_RUN:
        # 同凭据误配守卫: 跟主账户或 bench 任何一个相同 → 拒绝启动
        skey = (os.environ.get("SHADOW_POLY_PRIVATE_KEY") or "").strip().lower()
        if (skey and skey == (os.environ.get("POLY_PRIVATE_KEY") or "").strip().lower()) or \
           (_funder and _funder.lower() == (os.environ.get("POLY_FUNDER") or "").strip().lower()):
            log.error("[shadow] 🔴 SHADOW 凭据与主账户相同 — 拒绝启动 (防在主账户上乱下单乱止损)")
            return
        if (skey and skey == (os.environ.get("BENCH_POLY_PRIVATE_KEY") or "").strip().lower()) or \
           (_funder and _funder.lower() == (os.environ.get("BENCH_POLY_FUNDER") or "").strip().lower()):
            log.error("[shadow] 🔴 SHADOW 凭据与 bench 二号账户相同 — 拒绝启动")
            return
    prev_mode = _state_get("mode")
    if not _state_get("start_at") or (prev_mode == "dry" and mode == "real"):
        _state_set("start_at", _utcnow())   # 首次激活 / dry→真钱切换: 只买此后的新推荐 (存量不补, 用户拍板)
        log.info(f"[shadow] start_at 已{'重置' if prev_mode else '落库'} ({mode}) — 只买今后的新推荐")
    _state_set("mode", mode)
    if not DRY_RUN:
        _exe = _make_executor()
        if not getattr(_exe, "client", None):
            log.error("[shadow] 三号账户 CLOB client 初始化失败, 本次不启动 (查 SHADOW_POLY_* 凭据)")
            return
        log.info(f"[shadow] 三号账户已激活: funder={_funder[:10]}… 现金=${_cash()}")
    _thread_started = True
    threading.Thread(target=_loop, daemon=True).start()


def register_routes(app):
    from flask import jsonify

    @app.route("/api/shadow/status")
    def shadow_status():
        _ensure_tables()
        pos = _db_rows("SELECT * FROM shadow_positions ORDER BY id DESC LIMIT 100")
        done = _db_rows("SELECT COUNT(*) c FROM shadow_done")[0]["c"]
        return jsonify({"configured": is_configured(), "active": _thread_started, "dry_run": DRY_RUN,
                        "last_tick": _state_get("last_tick"),
                        "start_at": _state_get("start_at"), "mode": _state_get("mode"), "cash": _cash(),
                        "params": {"max_price": MAX_PRICE, "stake_usd": STAKE_USD,
                                   "stop_pct": STOP_PCT, "floor": FLOOR, "confirm": CONFIRM_ROUNDS},
                        "positions": pos, "done_count": done})

    @app.route("/api/shadow/scan_now", methods=["POST"])
    def shadow_scan_now():
        if not _thread_started:
            return jsonify({"ok": False, "message": "三号账户未激活 (缺 SHADOW_POLY_* 凭据或未开 DRY)"})
        threading.Thread(target=_consume_candidates, daemon=True).start()
        return jsonify({"ok": True, "message": "已在后台扫一轮候选"})
