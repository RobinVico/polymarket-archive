"""天气 bot 入口 — 日落后吃"当日最高温已锁定"的确定性收益.

原理: 日落后气温只降不升, 当日最高温已成事实, 但对应档位还在 0.9x 价位交易
→ 过全部护栏后买入该档 YES, 次日结算吃 1~5% 的确定性差价.

流程 (每 30s 心跳):
  1. ensure_plans   — 给每个启用城市建当日计划 (算日落 = 触发时刻)
  2. poll_weather   — METAR 每 10 分钟 / 香港天文台每 3 分钟, 观测入库
  3. tick_plans     — 到点的计划跑护栏, 全过 → 下单 (钱包没配 → 记 would_buy)
  4. watch_breach   — 买入后盯到当日结束, 万一夜间升温破档立刻红条报警
  5. resolution_sweep — 次日对结算, 记胜负和盈亏
"""
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from modules.gamma_client import install_polymarket_dns_guard, GammaError
from modules import config, db, decide, markets, wx
from modules.sunset import sunset_utc
from modules.version import VERSION

log = logging.getLogger("main")
TZ = timezone(timedelta(hours=config.TZ_OFFSET_H))

STATE = {"started_at": time.time(), "last_metar": 0.0, "last_hko": 0.0, "last_res_sweep": 0.0}


def now_utc():
    return datetime.now(timezone.utc)


def local_today():
    return datetime.now(TZ).date()


def iso(dt):
    return dt.isoformat() if dt else ""


def parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


class Bot:
    def __init__(self, trader):
        self.trader = trader

    # ===== 1. 当日计划 =====

    def ensure_plans(self):
        today = local_today()
        for key, cfg in config.CITIES.items():
            if not cfg["enabled"]:
                continue
            if db.get_plan(str(today), key):
                continue
            ss = sunset_utc(cfg["lat"], cfg["lon"], today, config.TZ_OFFSET_H)
            if not ss:
                continue
            fire = ss + timedelta(minutes=config.ENTRY_DELAY_MIN)
            dl_local = datetime(today.year, today.month, today.day,
                                config.DEADLINE_LOCAL_H, 30, tzinfo=TZ)
            db.create_plan(str(today), key,
                           event_slug=markets.event_slug(cfg["slug_city"], today),
                           sunset_utc=iso(ss), fire_utc=iso(fire),
                           deadline_utc=iso(dl_local.astimezone(timezone.utc)),
                           status="watching", reason="等日落")
            log.info(f"[{cfg['name']}] 今日计划: 日落 {ss.astimezone(TZ):%H:%M} → 触发点已排")

    # ===== 2. 气温轮询 =====

    def poll_weather(self):
        now = time.time()
        metar_map = {cfg["station"]: key for key, cfg in config.CITIES.items()
                     if cfg["enabled"] and cfg["source"] == "metar"}
        if metar_map and now - STATE["last_metar"] >= config.POLL_METAR_MIN * 60:
            STATE["last_metar"] = now
            try:
                n = wx.poll_metar(metar_map)
                log.info(f"METAR 更新 {n} 条 ({len(metar_map)} 站)")
            except Exception as e:
                log.warning(f"METAR 拉取失败: {e}")
        has_hko = any(cfg["enabled"] and cfg["source"] == "hko" for cfg in config.CITIES.values())
        if has_hko and now - STATE["last_hko"] >= config.POLL_HK_MIN * 60:
            STATE["last_hko"] = now
            try:
                wx.poll_hko()
            except Exception as e:
                log.warning(f"HKO 拉取失败: {e}")

    # ===== 3. 决策 =====

    def _effective_fire(self, plan):
        """日落触发点; 若市场 endDate(名义当地20:00) 早于日落 (如成都), 提前到停止接单前
        PRE_CUTOFF_MIN 分钟 (最早不早于日落前 45 分钟)."""
        fire = parse_iso(plan["fire_utc"])
        end = parse_iso(plan.get("end_date_utc") or "")
        if fire and end:
            cutoff = end - timedelta(minutes=config.PRE_CUTOFF_MIN)
            if fire > cutoff:
                return max(cutoff, fire - timedelta(minutes=45))
        return fire

    def tick_plans(self):
        now = now_utc()
        today_str = str(local_today())
        for plan in db.watching_plans():
            cfg = config.CITIES.get(plan["city"])
            if not cfg:
                continue
            if plan["local_date"] != today_str:
                db.update_plan(plan["id"], status="skipped", reason="过了当日窗口")
                continue
            deadline = parse_iso(plan["deadline_utc"])
            if deadline and now > deadline:
                db.update_plan(plan["id"], status="skipped",
                               reason=f"到 {config.DEADLINE_LOCAL_H}:30 仍未满足: {plan['reason']}")
                log.info(f"[{cfg['name']}] 当日放弃: {plan['reason']}")
                continue
            fire0 = parse_iso(plan["fire_utc"])
            if not fire0:
                continue
            # 日落前 45 分钟预拉事件 (endDate 决定成都类城市要不要提前)
            if not plan.get("end_date_utc") and now >= fire0 - timedelta(minutes=45):
                try:
                    ev = markets.fetch_event(plan["event_slug"])
                    if ev:
                        db.update_plan(plan["id"], end_date_utc=iso(ev["end_date"]),
                                       event_title=ev["title"])
                        plan["end_date_utc"] = iso(ev["end_date"])
                    else:
                        db.update_plan(plan["id"], reason="市场还没上线, 等着")
                except (GammaError, Exception) as e:
                    log.warning(f"[{cfg['name']}] 预拉事件失败: {e}")
            eff = self._effective_fire(plan)
            if eff and now < eff:
                stats = wx.day_stats(plan["city"], local_today())
                if stats:
                    db.update_plan(plan["id"], day_max=stats["max"], cur_temp=stats["cur"])
                continue
            self.decide_one(plan, cfg, now)

    def decide_one(self, plan, cfg, now):
        today = local_today()
        stats = wx.day_stats(plan["city"], today)
        try:
            ev = markets.fetch_event(plan["event_slug"])
        except Exception as e:
            db.update_plan(plan["id"], reason=f"拉市场失败: {e}", attempts=plan["attempts"] + 1)
            return
        if ev is None:
            db.update_plan(plan["id"], reason="市场不存在/还没上线",
                           attempts=plan["attempts"] + 1)
            return

        bint = bucket = top = None
        accepting = False
        ask = None
        if stats:
            bint = decide.bucket_int_for(cfg["source"], stats["max"])
            bucket = markets.pick_bucket(ev["buckets"], bint)
            top = markets.top_bucket(ev["buckets"])
            accepting = bool(bucket and bucket["accepting"])
            if bucket and bucket.get("token_yes"):
                ask = markets.best_ask_public(bucket["token_yes"])

        s0, _ = wx.local_day_bounds(today)
        coverage_ts = s0 + config.COVERAGE_BY_H * 3600
        spent = db.spent_on_date(str(today))
        halt = db.kv_get("halt", "0") == "1"

        ok, retryable, reason = decide.check_guards(
            now_ts=now.timestamp(), stats=stats, coverage_deadline_ts=coverage_ts,
            source=cfg["source"], bucket=bucket, top=top, accepting=accepting,
            ask=ask, spent_today=spent, halt=halt)

        fields = dict(day_max=stats["max"] if stats else None,
                      cur_temp=stats["cur"] if stats else None,
                      bucket=bint,
                      bucket_label=bucket["label"] if bucket else "",
                      token_id=(bucket.get("token_yes") or "") if bucket else "",
                      best_ask=ask, reason=reason, attempts=plan["attempts"] + 1)

        if not ok:
            if not retryable:
                fields["status"] = "skipped"
                log.info(f"[{cfg['name']}] 放弃当日: {reason}")
            db.update_plan(plan["id"], **fields)
            return

        # ===== 全部护栏通过 → 下单 =====
        tr = self.trader
        if tr.ready and not config.PAPER:
            res = tr.buy(bucket["token_yes"], config.ORDER_USD,
                         reason=f"weather {plan['city']} {bucket['label']}")
            if res["ok"]:
                fields.update(status="ordered", mode="real", order_usd=config.ORDER_USD,
                              filled_shares=res["shares"], filled_usd=res["usd"],
                              decided_at=db.utcnow_iso(), reason=res["msg"])
                log.info(f"[{cfg['name']}] ✅ 真钱买入 {bucket['label']}: {res['msg']}")
                db.add_alert(f"✅ {cfg['name']} 已买 {bucket['label']} @ {ask:.3f} — {res['msg']}")
            else:
                fields["reason"] = f"下单失败: {res['msg']}"
                if plan["attempts"] + 1 >= config.MAX_BUY_ATTEMPTS:
                    fields["status"] = "skipped"
                    db.add_alert(f"❌ {cfg['name']} 下单连续失败已放弃: {res['msg']}")
                log.warning(f"[{cfg['name']}] 下单失败 (第{plan['attempts'] + 1}次): {res['msg']}")
            db.update_plan(plan["id"], **fields)
        else:
            why = "PAPER模拟" if config.PAPER else "待钱包"
            est_shares = config.ORDER_USD / ask
            est_fee = decide.fee_usd(ask, est_shares)
            fields.update(status="would_buy", mode="paper", order_usd=config.ORDER_USD,
                          decided_at=db.utcnow_iso(),
                          reason=(f"{why} — 本该以 {ask:.3f} 买 {bucket['label']} "
                                  f"(${config.ORDER_USD:g}, 估费 ${est_fee:.4f})"))
            log.info(f"[{cfg['name']}] 📝 would_buy {bucket['label']} @ {ask:.3f} ({why})")
            db.update_plan(plan["id"], **fields)

    # ===== 4. 买后盯破档 =====

    def watch_breach(self):
        today = local_today()
        for plan in db.plans_for_date(str(today)):
            if plan["status"] not in ("ordered", "would_buy") or plan["breached"]:
                continue
            cfg = config.CITIES.get(plan["city"])
            if not cfg or plan["bucket"] is None:
                continue
            stats = wx.day_stats(plan["city"], today)
            if not stats:
                continue
            lbl = plan["bucket_label"] or ""
            if lbl.startswith("≥"):   # 最高档往上不可能破
                continue
            try:
                hi = int(lbl.replace("≤", "").replace("°C", ""))
            except ValueError:
                continue
            cur_int = decide.bucket_int_for(cfg["source"], stats["max"])
            if cur_int > hi:
                db.update_plan(plan["id"], breached=1, day_max=stats["max"])
                msg = (f"🚨 {cfg['name']} 买入后升温破档! 当日最高已到 {stats['max']:.1f}° "
                       f"(买的是 {lbl} 档) — 考虑手动处理")
                db.add_alert(msg)
                log.warning(msg)
            else:
                db.update_plan(plan["id"], day_max=stats["max"], cur_temp=stats["cur"])

    # ===== 5. 结算 =====

    def resolution_sweep(self):
        if time.time() - STATE["last_res_sweep"] < config.RESOLUTION_SWEEP_MIN * 60:
            return
        STATE["last_res_sweep"] = time.time()
        for plan in db.pending_resolution():
            try:
                ev = markets.fetch_event(plan["event_slug"])
            except Exception:
                continue
            if not ev or not ev["closed"]:
                continue
            win = markets.winning_bucket(ev["buckets"])
            if not win:
                db.update_plan(plan["id"], status="void", resolved_at=db.utcnow_iso(),
                               reason="事件已关闭但找不到赢家档")
                continue
            won = (win["label"] == plan["bucket_label"])
            # 手续费: taker 5%, 成交时收 (win/lose 都已付), 见 config.FEE_RATE_BPS
            if plan["status"] == "ordered":
                entry = (plan["filled_usd"] / plan["filled_shares"]) if plan["filled_shares"] else 1.0
                fee = decide.fee_usd(entry, plan["filled_shares"] or 0)
                pnl = (plan["filled_shares"] - plan["filled_usd"] - fee) if won \
                    else (-plan["filled_usd"] - fee)
            else:
                ask = plan["best_ask"] or 1.0
                shares = plan["order_usd"] / ask
                fee = decide.fee_usd(ask, shares)
                pnl = (shares - plan["order_usd"] - fee) if won else (-plan["order_usd"] - fee)
            db.update_plan(plan["id"], status="won" if won else "lost",
                           winning_label=win["label"], resolved_at=db.utcnow_iso(), pnl=pnl)
            cfg = config.CITIES.get(plan["city"], {})
            tag = "真钱" if plan["mode"] == "real" else "模拟"
            msg = (f"{'🟢 赢' if won else '🔴 输'} [{tag}] {cfg.get('name', plan['city'])} "
                   f"{plan['local_date']}: 买 {plan['bucket_label']}, 结算 {win['label']}, "
                   f"盈亏 {pnl:+.2f}")
            log.info(msg)
            if not won:
                db.add_alert(msg)

    # ===== 主循环 =====

    def loop(self):
        while True:
            for step in (self.ensure_plans, self.poll_weather, self.tick_plans,
                         self.watch_breach, self.resolution_sweep):
                try:
                    step()
                except Exception:
                    log.exception(f"{step.__name__} 异常")
            time.sleep(config.HEARTBEAT_SEC)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(os.path.join(config.ROOT, "bot.log"), encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)])
    install_polymarket_dns_guard()
    db.init_db()

    from modules.trader import Trader
    tr = Trader.get()
    enabled = [c["name"] for c in config.CITIES.values() if c["enabled"]]
    mode = "PAPER" if config.PAPER else ("真钱" if tr.ready else "待钱包(只记录不下单)")
    log.info(f"🌤️ 天气 bot v{VERSION} 启动 | 模式={mode} | 城市={'/'.join(enabled)} | "
             f"策略: 日落即下单 · 现温比当日最高低≥{config.TEMP_MARGIN_C:g}°C · "
             f"买价 {config.PRICE_MIN:g}~{config.PRICE_MAX:g} · ${config.ORDER_USD:g}/市场 · "
             f"日上限 ${config.DAILY_CAP_USD:g} · 港档=floor")

    from modules.dashboard import create_app
    app = create_app(tr, STATE)
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=config.PORT, debug=False, use_reloader=False),
        daemon=True).start()
    log.info(f"dashboard: http://localhost:{config.PORT}")

    Bot(tr).loop()


if __name__ == "__main__":
    main()
