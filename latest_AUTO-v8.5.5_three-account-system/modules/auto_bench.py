"""AUTO Bench — 第二账户「纯测 AI 准确率」基准策略 (用户 2026-07-23 拍板)。

目的: 把主策略的"提前卖出"变量拿掉, 用真钱测同一条 GLM 选品管道的**裸预测准确率**
(背景: 2026-07-23 分析发现 方向对 75% vs 落袋只 47%, 缺一个对照组)。

规则手册 (全部写死, 用户拍板):
  1. 信号源 = 共享的 auto_candidates 表 (跟主策略同一份 GLM 输出), 一字不改一个不漏 —
     含主策略因 40~85 分流送测试仓的那些, bench 全部真买。
  2. 推荐一出现 → 第二账户按执行瞬间市价买入推荐方向, 每仓固定 $2 (BENCH_USD_PER_POS)。
     不设漂移闸/不设任何别的门槛 — 方向准确率跟买价无关。
  3. 买完锁死: 无重评/无止盈/无任何更新。只有两种结局: 市场结算, 或 亏到 -30% 瞬时清仓
     (BENCH_STOP_LOSS_PCT, 用户原话"一旦亏到30%就直接卖", 单次观察即触发)。
  4. 跳过 (不买): 黑名单标记候选 (用户拍板"直接不卖" = 完全忽略、不买也不打分) /
     同市场已持同方向 (跳过) / 同市场已持反方向 (不对锁 → 只记 score_only 行等结算打分, 用户拍板) /
     宇宙闸不过 (防幻觉 slug) / 候选超 24h / 现金不足 (点名记日志绝不静默)。
  5. 双台账打分 (公平性的核心): 每仓记两本账 —
     钱的账 = 实际盈亏 (含 -30% 止损割掉的);
     AI 预测的账 = **哪怕被止损卖了, 照样等市场结算后判对错** → 止损保护本金但不污染准确率。

双账户隔离 (Plan 验证过的安全设计, 一条都不能少):
  - bench 绝不碰 Executor.get() (那是主账户单例); 用 env 临时换成 BENCH_POLY_* 直接构造第二个
    Executor 实例 (构造必须在 autobot 主线程、app.run 之前 — 避开 dashboard.py 运行时读
    POLY_FUNDER 的竞态), finally 原样恢复 env。
  - 绝不用 exe.get_positions() (它用模块级 FUNDER 全局 = 主账户) / get_cash_balance()
    (它写 Executor._live_cash 类属性 → 会把 bench 现金漏进主页面缓存) — bench 自带
    _positions()/_cash() 实现。buy()/sell() 用 self.client → 实例正确, 放心复用
    (整数股步长/negRisk/tick 的老逻辑全在里面)。
  - 同凭据误配守卫: BENCH 凭据 == 主账户 → 拒绝启动 (否则会在主账户上乱下单乱止损!)。
  - 主 monitor/重评 天然看不见 bench 仓 (它们走主账户 FUNDER) — 零互相干扰。

BENCH_DRY_RUN=1 = 纸上模拟 (不构造下单实例、不花钱, 假成交走公开盘口), 上真钱前 E2E 用;
dry 行打 dry=1 标记, /bench 钱的统计过滤掉它们 (预测打分照算 — 预测本身是真的)。
"""
import os
import re
import time
import logging
import threading
from datetime import datetime, timezone

import requests as rq

log = logging.getLogger("auto_bench")

DATA_API = "https://data-api.polymarket.com"

USD_PER_POS = float(os.environ.get("BENCH_USD_PER_POS", "2"))
STOP_PCT = float(os.environ.get("BENCH_STOP_LOSS_PCT", "0.30"))
DRY_RUN = os.environ.get("BENCH_DRY_RUN", "0").strip() in ("1", "true", "True")
CAND_TTL_H = 24.0
# Plan 验证风险5: $2 请求经整数股步长凑整最坏可成交到 ~$4 (0.001-tick 市场 step=10) → 现金门槛留 $5
CASH_MIN = 5.0
CURSOR_KEY = "auto_bench_last_cand_id"

_bench_exe = None          # 第二账户 Executor 实例 (start_bench 在主线程构造)
_funder = (os.environ.get("BENCH_POLY_FUNDER") or "").strip()
_pos_cache = (0.0, None)   # bench 自己的仓位缓存 (绝不用 Executor 类属性缓存)
_miss = {}                 # row_id → 连续几拍在仓位里找不到 (风险2: 结算自动赎回/手动卖 判别)
_sell_fail = {}            # row_id → 连续卖出失败次数
_sell_skip_until = {}      # row_id → 退避到什么时刻再试卖
_last_no_cash_evt = 0.0


def is_configured():
    if DRY_RUN:
        return True
    return bool((os.environ.get("BENCH_POLY_PRIVATE_KEY") or "").strip()) and bool(_funder)


# ---------- DB (自建表, 不动 db.py) ----------

def _ensure_tables():
    from modules.db import get_conn
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS bench_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT, cand_id INTEGER UNIQUE, scan_slot TEXT, tag TEXT,
        slug TEXT, title TEXT, side TEXT, token_id TEXT,
        rec_price REAL, q REAL, confidence TEXT,
        status TEXT, dry INTEGER DEFAULT 0,
        entry_price REAL, size REAL, usd REAL,
        sold_size REAL DEFAULT 0, proceeds_usd REAL DEFAULT 0,
        exit_price REAL, exit_at TEXT, realized_pnl_usd REAL,
        resolved_at TEXT, final_outcome REAL, is_correct INTEGER,
        note TEXT)""")
    # bench 账户资产快照 (监控页资产曲线用; 2026-07-24 用户要独立监控页)
    conn.execute("""CREATE TABLE IF NOT EXISTS bench_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER,
        cash REAL, pos_value REAL, total REAL)""")
    # 追加列 (表已存在时 CREATE 不生效, ALTER 补; 已有列会报错=正常忽略):
    # end_date → 持仓面板"距结算"列; pos_cost → 曲线成本线 (照主页样式)
    for _alter in ("ALTER TABLE bench_positions ADD COLUMN end_date TEXT",
                   "ALTER TABLE bench_snapshot ADD COLUMN pos_cost REAL"):
        try:
            conn.execute(_alter)
        except Exception:
            pass
    conn.commit()
    conn.close()


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _db_rows(sql, args=()):
    from modules.db import get_conn
    conn = get_conn()
    cur = conn.execute(sql, args)
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    return rows


def _db_exec(sql, args=()):
    from modules.db import get_conn
    conn = get_conn()
    conn.execute(sql, args)
    conn.commit()
    conn.close()


def _init_cursor():
    """首启: 游标 = 当前最大候选 id — 只认从现在起的新推荐, 绝不回补历史 (防一开机狂买陈年候选)。"""
    from modules.db import get_app_state, set_app_state
    if get_app_state(CURSOR_KEY) is None:
        try:
            mx = _db_rows("SELECT COALESCE(MAX(id),0) AS m FROM auto_candidates")[0]["m"]
        except Exception:
            mx = 0
        set_app_state(CURSOR_KEY, int(mx))
        log.info(f"[bench] 首次启用: 游标初始化到候选 id={mx} (历史候选不回补, 只买今后的新推荐)")


# ---------- 第二账户 plumbing ----------

def build_bench_executor():
    """⚠️ 只能在 autobot 主线程、app.run 之前调用 (Plan 验证风险1)。
    env 临时换 BENCH_POLY_* → 直接 Executor() 构造 (不碰 .get() 单例) → finally 原样恢复。"""
    global _bench_exe
    if DRY_RUN:
        log.info("[bench] DRY_RUN=1 纸上模拟模式: 不构造真实下单实例, 不花一分钱")
        return True
    key = (os.environ.get("BENCH_POLY_PRIVATE_KEY") or "").strip()
    sig = (os.environ.get("BENCH_POLY_SIGNATURE_TYPE") or "3").strip()
    if not key or not _funder:
        return False
    # 同凭据误配守卫 (Plan 新洞1, critical): bench 凭据 == 主账户 → 拒绝启动
    main_key = (os.environ.get("POLY_PRIVATE_KEY") or "").strip()
    main_fun = (os.environ.get("POLY_FUNDER") or "").strip()
    if key == main_key or _funder.lower() == main_fun.lower():
        log.error("[bench] 🔴 BENCH_POLY_* 凭据与主账户相同 — 拒绝启动 bench (防止在主账户上乱下单/乱止损)")
        try:
            from modules.db import log_event
            log_event("bench_disabled", "bench", "🔴 BENCH 凭据与主账户相同, bench 拒绝启动 (改 .env 后重启)")
        except Exception:
            pass
        return False
    from modules.executor import Executor
    swap = {"POLY_PRIVATE_KEY": key, "POLY_FUNDER": _funder, "POLY_SIGNATURE_TYPE": sig}
    saved = {k: os.environ.get(k) for k in swap}
    try:
        os.environ.update(swap)
        exe = Executor()   # 直接构造 — Executor.get() 的 _instance 单例不受影响 (它只在 get() 里赋值)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    if not getattr(exe, "client", None):
        log.error("[bench] 🔴 第二账户 client 构造失败 (凭据错/网络?), bench 不启动 (修好后重启)")
        return False
    _bench_exe = exe
    log.info(f"[bench] 第二账户下单实例就绪 (funder …{_funder[-6:]}, sig={sig})")
    return True


def _positions(fresh=False):
    """bench 账户实时仓位 (data-api 直查 BENCH funder, 自带 35s 缓存)。
    ⚠️ 出错返回 None (故意跟 executor 的"出错返回 []"不同 — Plan 风险2: [] 会被误读成"仓全没了")。"""
    global _pos_cache
    if not fresh and _pos_cache[1] is not None and time.time() - _pos_cache[0] < 35:
        return _pos_cache[1]
    try:
        r = rq.get(f"{DATA_API}/positions",
                   params={"user": _funder, "limit": 200, "sizeThreshold": 0}, timeout=15)
        raw = r.json()
        out = []
        for p in (raw if isinstance(raw, list) else []):
            out.append({"asset": p.get("asset"), "size": float(p.get("size") or 0),
                        "avg_price": float(p.get("avgPrice") or 0),
                        "cur_price": float(p.get("curPrice") or 0),
                        "title": p.get("title") or ""})
        _pos_cache = (time.time(), out)
        return out
    except Exception as e:
        log.warning(f"[bench] 仓位拉取失败 (本轮跳过): {e}")
        return None


def _cash():
    """bench 账户现金 (走 bench client; 复刻 executor.get_cash_balance **但绝不写 Executor._live_cash
    类属性** — 写了会把 bench 现金漏进主页面缓存, Plan 验证风险1)。失败/DRY 返回 None。"""
    if DRY_RUN or _bench_exe is None:
        return None
    try:
        from py_clob_client_v2 import BalanceAllowanceParams, AssetType
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        r = _bench_exe.client.get_balance_allowance(params)
        bal_raw = r.get("balance") if isinstance(r, dict) else getattr(r, "balance", None)
        return float(bal_raw) / 1_000_000 if bal_raw is not None else None
    except Exception as e:
        log.warning(f"[bench] 现金查询失败: {e}")
        return None


def _best_bid(token_id):
    try:
        book = rq.get("https://clob.polymarket.com/book", params={"token_id": token_id}, timeout=10).json()
        bids = sorted((float(b["price"]) for b in book.get("bids", [])), reverse=True)
        return bids[0] if bids else None
    except Exception:
        return None


# ---------- 消费候选 (5s 一轮) ----------

def _row_exists(cand_id):
    return bool(_db_rows("SELECT 1 FROM bench_positions WHERE cand_id=?", (cand_id,)))


def _insert_row(row, status, token_id=None, note="", dry=0):
    """UNIQUE(cand_id) + INSERT OR IGNORE = 幂等 (Plan 风险6: 崩溃只会丢一笔买入, 绝不重复买)。"""
    _db_exec("""INSERT OR IGNORE INTO bench_positions
        (created_at, cand_id, scan_slot, tag, slug, title, side, token_id,
         rec_price, q, confidence, status, dry, note, end_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_utcnow(), row["id"], row.get("scan_slot"), row.get("tag"), row["slug"],
         (row.get("title") or "")[:200], (row.get("side") or "").upper(), token_id,
         row.get("cur_price"), row.get("q"), row.get("confidence"),
         status, dry, note[:200], (row.get("end_date") or "")[:20]))


def _consume_once():
    from modules.db import get_app_state, set_app_state
    cur_id = int(get_app_state(CURSOR_KEY) or 0)
    try:
        rows = _db_rows("SELECT * FROM auto_candidates WHERE id>? ORDER BY id", (cur_id,))
    except Exception:
        return   # auto_candidates 还没建 (discovery 没跑过)
    for row in rows:
        try:
            _process_candidate(row)
        except Exception as e:
            log.exception(f"[bench] 候选处理异常 cand{row['id']}")
            # Plan 新洞2: 异常候选记 error 行留痕 (游标过了就再也不看, 不留痕 = 准确率丢样本还不知道)
            try:
                _insert_row(row, status=f"error:{str(e)[:60]}")
            except Exception:
                pass
        set_app_state(CURSOR_KEY, row["id"])


def _process_candidate(row):
    from modules.db import _parse_iso_to_aware, log_event
    from modules.auto_trader import _in_universe, _resolve_token, _fresh_ask
    global _last_no_cash_evt
    cid, slug, side = row["id"], row["slug"], (row.get("side") or "").upper()
    label = f"cand{cid} {slug[:36]} {side}"
    if _row_exists(cid):
        return
    # 24h 保鲜 (跟主策略同 TTL; 停机重启后不拿旧行情推荐下今天的单)
    try:
        age_h = (datetime.now(timezone.utc) - _parse_iso_to_aware(row["created_at"])).total_seconds() / 3600.0
    except Exception:
        age_h = 0.0
    if age_h > CAND_TTL_H:
        log.info(f"[bench] ⏳ 跳过超{int(CAND_TTL_H)}h旧候选: {label}")
        return
    # 宇宙闸 (防幻觉 slug, 数据卫生) + 黑名单 (用户拍板: 完全忽略, 不买也不打分)
    ok_u, why, is_bl = _in_universe(row)
    if not ok_u:
        log.warning(f"[bench] ⛔ 宇宙外跳过: {label} — {why}")
        return
    if is_bl:
        log.info(f"[bench] 🚫 黑名单推荐, bench 完全忽略 (用户拍板): {label}")
        return
    token, closed, _toks = _resolve_token(slug, side)
    if not token:
        _insert_row(row, status="error:gamma查不到token", note=why)
        log.warning(f"[bench] gamma 查不到 token, 记 error 行: {label}")
        return
    if closed:
        log.info(f"[bench] 市场已关闭, 跳过: {label}")
        return
    # 同市场持有检查 (查自己的表, 不靠有延迟的 data-api — Plan 风险6)
    held = _db_rows("SELECT side FROM bench_positions WHERE slug=? AND status IN ('pending','open')", (slug,))
    if held:
        if any((h["side"] or "").upper() == side for h in held):
            log.info(f"[bench] 已持同市场同方向, 跳过重复: {label}")
            return
        # 反方向: 不对锁 (用户拍板) → 只记 score_only 行, 结算后照样打分
        _insert_row(row, status="score_only", token_id=token, note="反方向推荐, 不对锁只打分")
        log.info(f"[bench] 🔁 反方向推荐 → 不买只记分: {label}")
        return
    # 现金门槛 (Plan 风险5: $2 请求最坏成交 ~$4 → 要求 $5 余量)
    c = _cash()
    if c is not None and c < CASH_MIN:
        log.warning(f"[bench] 💸 现金不足 (${c:.2f} < ${CASH_MIN:g}), 跳过: {label} — 请给 bench 账户充值")
        if time.time() - _last_no_cash_evt > 3600:
            _last_no_cash_evt = time.time()
            try:
                log_event("bench_no_cash", "bench", f"bench 账户现金 ${c:.2f} 不足, 推荐被跳过 — 请充值")
            except Exception:
                pass
        return
    # pending 行先落库 → 再动钱 (Plan 风险6 铁不变式: 崩溃只丢买入, 绝不重复买)
    _insert_row(row, status="pending", token_id=token, dry=1 if DRY_RUN else 0)
    if DRY_RUN:
        entry = _fresh_ask(token) or float(row.get("cur_price") or 0)
        if not entry or not (0 < entry < 1):
            _db_exec("UPDATE bench_positions SET status='error:dry无盘口' WHERE cand_id=?", (cid,))
            return
        size = max(1, int(round(USD_PER_POS / entry)))
        usd = round(size * entry, 4)
        _db_exec("""UPDATE bench_positions SET status='open', entry_price=?, size=?, usd=? WHERE cand_id=?""",
                 (entry, float(size), usd, cid))
        log.info(f"[bench] 🧪(dry) 模拟买入 {size}股 @ {entry:.3f} ≈ ${usd:.2f}: {label}")
        return
    ok, msg = _bench_exe.buy(token, USD_PER_POS, reason=f"bench:cand{cid}")
    if not ok:
        _db_exec("UPDATE bench_positions SET status=? WHERE cand_id=?", (("error:buy:" + str(msg))[:120], cid))
        log.warning(f"[bench] 买入失败 {label}: {msg}")
        return
    # msg 固定格式 "买成功: 6.00股 @ 67.0% ≈ $4.02" — 股数/花费是实际值; @后面是限价别用 (Plan 风险4)
    m_sh = re.search(r"([0-9]+(?:\.[0-9]+)?)股", str(msg))
    m_usd = re.search(r"≈ \$([0-9]+(?:\.[0-9]+)?)", str(msg))
    shares = float(m_sh.group(1)) if m_sh else 0.0
    usd = float(m_usd.group(1)) if m_usd else 0.0
    if shares > 0 and usd > 0:
        entry = usd / shares
    else:
        # 解析兜底: 等 data-api 同步 (最多 60s), 再不行用盘口 ask
        entry, shares, usd = None, 0.0, USD_PER_POS
        for _ in range(6):
            time.sleep(10)
            for p in (_positions(fresh=True) or []):
                if p["asset"] == token:
                    entry, shares = p["avg_price"], p["size"]
                    usd = round(entry * shares, 4)
                    break
            if entry:
                break
        if not entry:
            entry = _fresh_ask(token) or float(row.get("cur_price") or 0.5)
            shares = shares or round(USD_PER_POS / entry, 2)
    _db_exec("""UPDATE bench_positions SET status='open', entry_price=?, size=?, usd=? WHERE cand_id=?""",
             (entry, shares, usd, cid))
    log.info(f"[bench] 🟢 买入 {shares:g}股 @ {entry:.3f} ≈ ${usd:.2f}: {label}")
    try:
        log_event("bench_buy", row.get("title") or slug, f"[bench] 买入 ${usd:.2f} {side} @ {entry:.3f} (固定$2策略)")
    except Exception:
        pass


# ---------- 止损巡检 (30s 一轮; 唯一的卖出规则 = 亏≥30% 瞬时清仓) ----------

def _promote_or_expire_pending():
    """崩溃在「买入成功↔落库」窗口里的 pending 行: 仓位出现 → 补记 open; 15min 还没出现 → error (绝不重买)。"""
    rows = _db_rows("SELECT * FROM bench_positions WHERE status='pending'")
    if not rows:
        return
    pos = _positions()
    for r in rows:
        p = next((x for x in (pos or []) if x["asset"] == r["token_id"]), None)
        if p and p["size"] > 0:
            _db_exec("UPDATE bench_positions SET status='open', entry_price=?, size=?, usd=? WHERE id=?",
                     (p["avg_price"], p["size"], round(p["avg_price"] * p["size"], 4), r["id"]))
            log.info(f"[bench] pending 行补记为 open (data-api 找到仓): {r['slug'][:36]}")
        else:
            try:
                from modules.db import _parse_iso_to_aware
                age_min = (datetime.now(timezone.utc) - _parse_iso_to_aware(r["created_at"])).total_seconds() / 60
            except Exception:
                age_min = 99
            if age_min > 15:
                _db_exec("UPDATE bench_positions SET status='error:pending-unknown' WHERE id=?", (r["id"],))
                log.warning(f"[bench] pending 行 15min 未见仓位, 标 error (绝不重买): {r['slug'][:36]}")


def _stop_loss_once():
    from modules.resolution_check import check_resolution
    _promote_or_expire_pending()
    rows = _db_rows("SELECT * FROM bench_positions WHERE status='open'")
    if not rows:
        return
    if DRY_RUN:
        # dry 仓管理: 公开盘口 bid 判 -30%, 假卖
        for r in rows:
            bid = _best_bid(r["token_id"])
            if not bid or not r.get("entry_price"):
                continue
            if (r["entry_price"] - bid) / r["entry_price"] >= STOP_PCT:
                _db_exec("""UPDATE bench_positions SET status='stopped', exit_price=?, exit_at=?,
                            sold_size=size, proceeds_usd=?, realized_pnl_usd=? WHERE id=?""",
                         (bid, _utcnow(), round(bid * r["size"], 4),
                          round(bid * r["size"] - r["usd"], 4), r["id"]))
                log.info(f"[bench] 🧪(dry) -30% 触发假卖 @ {bid:.3f}: {r['slug'][:36]}")
        return
    pos = _positions()
    if pos is None:
        return   # data-api 抖动, 本轮跳过 (绝不把"拉取失败"当"仓全没了")
    by_tok = {p["asset"]: p for p in pos}
    for r in rows:
        rid = r["id"]
        p = by_tok.get(r["token_id"])
        if p is None or p["size"] <= 0:
            # 仓位消失: 结算自动赎回 or 手动卖 (Plan 风险2) — 连续 3 拍才动作, 只查一次 gamma
            _miss[rid] = _miss.get(rid, 0) + 1
            if _miss[rid] == 3:
                res = None
                try:
                    res = check_resolution(r["token_id"], r["side"], r["slug"])
                except Exception:
                    pass
                if res:
                    pass   # 市场已结算 → 留给打分轮统一收尾 (它会算 realized + is_correct)
                else:
                    _db_exec("UPDATE bench_positions SET status='vanished', note=? WHERE id=?",
                             ("仓位消失但市场未结算 (账户2手动卖出?), 预测仍等结算打分", rid))
                    log.warning(f"[bench] ⚠️ 仓位消失且市场未结算, 标 vanished: {r['slug'][:36]}")
            continue
        _miss.pop(rid, None)
        # 部分成交侦测: 实际持仓 < 账面剩余 → 差额按当前 bid 计提 proceeds (近似, Plan 风险3)
        expected = (r["size"] or 0) - (r["sold_size"] or 0)
        if p["size"] < expected - 0.009:
            delta = expected - p["size"]
            px = _best_bid(r["token_id"]) or p["cur_price"] or 0
            _db_exec("UPDATE bench_positions SET sold_size=sold_size+?, proceeds_usd=proceeds_usd+? WHERE id=?",
                     (delta, round(delta * px, 4), rid))
            r["sold_size"] = (r["sold_size"] or 0) + delta
            r["proceeds_usd"] = (r["proceeds_usd"] or 0) + round(delta * px, 4)
            log.info(f"[bench] 检测到部分卖出 Δ{delta:g}股 @~{px:.3f}, 已计提: {r['slug'][:36]}")
        # -30% 判定 (用户拍板: 瞬时, 单次观察即触发)。data-api cur 预筛 + 同一拍盘口 bid 确认
        # (bid 是真实能卖到的价, 防 curPrice 假象 — 老项目 v5.1 教训)。
        avg = p["avg_price"] or r["entry_price"] or 0
        if avg <= 0:
            continue
        if (avg - (p["cur_price"] or 0)) / avg < STOP_PCT:
            continue
        if time.time() < _sell_skip_until.get(rid, 0):
            continue
        bid = _best_bid(r["token_id"])
        if not bid or (avg - bid) / avg < STOP_PCT:
            continue
        live_size = p["size"]
        # 尘埃仓守卫 (Plan 风险3): 剩余价值 < $0.05 卖不动 → 直接关行, 剩余留给结算打分
        if live_size * bid < 0.05:
            _db_exec("UPDATE bench_positions SET status='stopped', exit_price=?, exit_at=?, note=? WHERE id=?",
                     (bid, _utcnow(), "尘埃仓强关 (剩余<$0.05 卖不动)", rid))
            continue
        okb = _bench_exe.sell(r["token_id"], live_size, reason=f"bench:stop30:{rid}")
        if okb:
            sold = (r["sold_size"] or 0) + live_size
            proceeds = (r["proceeds_usd"] or 0) + round(live_size * bid, 4)
            remaining = (r["size"] or 0) - sold
            realized = round(proceeds - (r["usd"] or 0), 4) if remaining < 0.01 else None
            _db_exec("""UPDATE bench_positions SET status='stopped', exit_price=?, exit_at=?,
                        sold_size=?, proceeds_usd=?, realized_pnl_usd=? WHERE id=?""",
                     (bid, _utcnow(), sold, proceeds, realized, rid))
            _sell_fail.pop(rid, None)
            log.warning(f"[bench] 🔴 -30% 止损清仓 {live_size:g}股 @~{bid:.3f}: {r['slug'][:36]} "
                        f"(预测仍等结算打分)")
            try:
                from modules.db import log_event
                log_event("bench_stop", r.get("title") or r["slug"],
                          f"[bench] -30% 止损卖出 @~{bid:.3f} (预测照样等结算打分)")
            except Exception:
                pass
        else:
            _sell_fail[rid] = _sell_fail.get(rid, 0) + 1
            log.warning(f"[bench] 止损卖出未完成 (第{_sell_fail[rid]}次, 可能部分成交/盘口薄): {r['slug'][:36]}")
            if _sell_fail[rid] >= 3:
                _sell_skip_until[rid] = time.time() + 600   # 退避 10 分钟 (Plan 风险3)


# ---------- 结算打分 (1h 一轮; 准确率的唯一真相源) ----------

def _score_once():
    """所有还没打分的行 (open/stopped/score_only/vanished) 逐个问 gamma 结算了没。
    open 行结算 → 按 终值 收尾钱账; stopped/score_only/vanished → 只补预测对错。
    上限 40 行/轮 最老优先 (Plan 新洞6: 远期 score_only 会攒, 别一轮打爆 gamma)。"""
    from modules.resolution_check import check_resolution
    from modules.auto_trader import _resolve_token
    rows = _db_rows("""SELECT * FROM bench_positions WHERE final_outcome IS NULL
                       AND status IN ('open','stopped','score_only','vanished')
                       ORDER BY created_at LIMIT 40""")
    n_scored = 0
    for r in rows:
        tok = r["token_id"]
        if not tok:   # score_only 插入时 gamma 恰好挂了 → 补查 (Plan 新洞3)
            try:
                tok, _, _ = _resolve_token(r["slug"], r["side"])
                if tok:
                    _db_exec("UPDATE bench_positions SET token_id=? WHERE id=?", (tok, r["id"]))
            except Exception:
                tok = None
        if not tok:
            continue
        try:
            res = check_resolution(tok, r["side"], r["slug"])
        except Exception:
            res = None
        if not res:
            continue
        fo = float(res["final_outcome"])   # 已是 持有方向 的 0/1
        ic = 1 if fo >= 0.5 else 0
        sets = ["final_outcome=?", "is_correct=?", "resolved_at=?"]
        args = [fo, ic, res.get("resolved_at") or _utcnow()]
        if r["status"] == "open":
            remaining = (r["size"] or 0) - (r["sold_size"] or 0)
            realized = round((r["proceeds_usd"] or 0) + fo * remaining - (r["usd"] or 0), 4)
            sets += ["status='resolved'", "exit_price=?", "exit_at=?", "realized_pnl_usd=?"]
            args += [fo, args[2], realized]
        elif r["status"] == "stopped" and r["realized_pnl_usd"] is None:
            # 止损后有尘埃剩余的: 按终值补齐钱账
            remaining = (r["size"] or 0) - (r["sold_size"] or 0)
            realized = round((r["proceeds_usd"] or 0) + fo * remaining - (r["usd"] or 0), 4)
            sets += ["realized_pnl_usd=?"]
            args += [realized]
        args.append(r["id"])
        _db_exec(f"UPDATE bench_positions SET {', '.join(sets)} WHERE id=?", tuple(args))
        n_scored += 1
        log.info(f"[bench] 📊 结算打分: {r['slug'][:36]} {r['side']} → {'✅对' if ic else '❌错'} "
                 f"(status={r['status']})")
        try:
            from modules.db import log_event
            log_event("bench_resolve", r.get("title") or r["slug"],
                      f"[bench] 结算: 预测{'对✅' if ic else '错❌'} ({r['side']} → {fo:g})")
        except Exception:
            pass
        time.sleep(0.4)   # 对 gamma 温柔点
    if n_scored:
        log.info(f"[bench] 本轮结算打分 {n_scored} 行")


# ---------- 主循环 + 启动 ----------

def _snapshot_once():
    """bench 账户资产快照 (曲线用): total = 现金 + 账户全部持仓现值 (老账户无遗留仓, = bench 仓)。
    cash/positions 任一拉不到就跳过本次 (绝不写半残行污染曲线, 学主 bot 的守卫)。"""
    if DRY_RUN:
        return
    c = _cash()
    pos = _positions()
    if c is None or pos is None:
        return
    pv = sum((p["cur_price"] or 0) * (p["size"] or 0) for p in pos)
    pc = sum((p["avg_price"] or 0) * (p["size"] or 0) for p in pos)   # 成本口径 → 曲线成本线 (照主页)
    _db_exec("INSERT INTO bench_snapshot (ts, cash, pos_value, pos_cost, total) VALUES (?,?,?,?,?)",
             (int(time.time()), round(c, 4), round(pv, 4), round(pc, 4), round(c + pv, 4)))


def run_loop():
    _ensure_tables()
    _init_cursor()
    log.info(f"[bench] 基准策略线程启动: dry={int(DRY_RUN)} | ${USD_PER_POS:g}/仓 固定 | "
             f"唯一卖出=亏{STOP_PCT*100:.0f}%瞬时清仓 | 无重评无止盈 | 持有到结算 | 双台账(钱+预测)")
    n = 0
    while True:
        try:
            _consume_once()
        except Exception:
            log.exception("[bench] 消费轮异常 (继续)")
        if n % 6 == 0:       # 30s
            try:
                _stop_loss_once()
            except Exception:
                log.exception("[bench] 止损轮异常 (继续)")
        if n % 120 == 0:     # 10min: 资产快照 (n=0 启动即打一个点, 曲线立刻有种子)
            try:
                _snapshot_once()
            except Exception:
                log.exception("[bench] 快照异常 (继续)")
        if n % 720 == 0:     # 1h
            try:
                _score_once()
            except Exception:
                log.exception("[bench] 打分轮异常 (继续)")
        n += 1
        time.sleep(5)


def start_bench():
    """autobot 主线程调用 (app.run 之前!): 构造第二账户实例 + 起 daemon 线程。未配置 → 点名跳过。"""
    if not is_configured():
        log.info("[bench] 未配置 BENCH_POLY_PRIVATE_KEY/BENCH_POLY_FUNDER (也非 DRY_RUN) → bench 不启动")
        return False
    if not build_bench_executor():
        return False
    threading.Thread(target=run_loop, daemon=True).start()
    return True


# ---------- /bench 页 + API ----------

def _bucket(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "?"
    if p < 0.2:
        return "<20¢"
    if p < 0.4:
        return "20-40¢"
    if p < 0.6:
        return "40-60¢"
    if p < 0.8:
        return "60-80¢"
    return "≥80¢"


def _summary():
    rows = _db_rows("SELECT * FROM bench_positions ORDER BY id DESC")
    money = [r for r in rows if not r["dry"] and r["status"] in ("open", "stopped", "resolved")]
    realized = sum(r["realized_pnl_usd"] or 0 for r in money if r["realized_pnl_usd"] is not None)
    # 未实现: open 行按 live cur (缓存) 或 entry
    pos = _positions() if not DRY_RUN else None
    by_tok = {p["asset"]: p for p in (pos or [])}
    unreal = 0.0
    for r in money:
        if r["status"] == "open":
            cur = (by_tok.get(r["token_id"]) or {}).get("cur_price") or r["entry_price"] or 0
            unreal += (cur - (r["entry_price"] or 0)) * (r["size"] or 0)
    scored = [r for r in rows if r["final_outcome"] is not None]
    acc = {}
    for r in scored:
        b = _bucket(r["entry_price"] if r["entry_price"] else r["rec_price"])
        d = acc.setdefault(b, [0, 0])
        d[0] += 1
        d[1] += r["is_correct"] or 0
    return {"rows": rows[:200], "n_total": len(rows),
            "n_open": sum(1 for r in rows if r["status"] == "open"),
            "n_stopped": sum(1 for r in rows if r["status"] == "stopped"),
            "n_resolved_scored": len(scored),
            "n_correct": sum(r["is_correct"] or 0 for r in scored),
            "realized": round(realized, 2), "unrealized": round(unreal, 2),
            "acc_buckets": {b: {"n": v[0], "correct": v[1]} for b, v in acc.items()},
            "dry_mode": DRY_RUN}


def register_routes(app):
    from flask import jsonify

    @app.route("/api/bench/summary")
    def bench_summary_api():
        _ensure_tables()
        return jsonify(_summary())

    @app.route("/api/bench/consume_now", methods=["POST"])
    def bench_consume_now():
        threading.Thread(target=_consume_once, daemon=True).start()
        return jsonify({"ok": True, "message": "bench 消费已在后台触发"})

    @app.route("/api/bench/score_now", methods=["POST"])
    def bench_score_now():
        threading.Thread(target=_score_once, daemon=True).start()
        return jsonify({"ok": True, "message": "bench 结算打分已在后台触发"})

