#!/usr/bin/env python3
"""
Polymarket Bot v2 — Claude Research Single Engine
"""
import time
import threading
import logging
from datetime import datetime
from pathlib import Path

from modules.claude_research import ClaudeResearch
from modules.risk_engine import RiskEngine
from modules.executor import Executor
from modules.position_monitor import PositionMonitor
from modules.phase_manager import daily_phase_check
from modules.prompts import DISCOVERY_PROMPT, REVIEW_PROMPT
from modules.browser_manager import BrowserManager
from modules.db import init_db, log_event, save_trade, get_current_phase

SCAN_HOURS = 4
MONITOR_MIN = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()])
log = logging.getLogger("main")


class TradingBot:
    def __init__(self):
        init_db()
        self.claude = ClaudeResearch()
        self.risk = RiskEngine()
        self.executor = Executor()
        self.monitor = PositionMonitor()

    def discover(self):
        log.info("=== Discovery cycle ===")
        try:
            positions = self.executor.get_positions()
            balance = self.executor.get_balance()
            pos_list = "\n".join(f"- {p['market_slug']} ({p['side']})" for p in positions) or "none"
            prompt = DISCOVERY_PROMPT.replace("{positions_list}", pos_list)

            log.info(f"Claude Research starting (balance=${balance:.2f}, {len(positions)} positions)...")
            response = self.claude.run(prompt, timeout_minutes=25)

            if not response:
                log.error("Claude Research returned nothing")
                log_event("error", "discovery", "no response")
                return

            Path("reports").mkdir(exist_ok=True)
            Path(f"reports/cr_{datetime.now():%Y%m%d_%H%M}.txt").write_text(response, encoding="utf-8")

            result = ClaudeResearch.extract_json(response)
            bets = result.get("bets", [])
            if not bets:
                log.info("No recommendations")
                log_event("scan", "none", result.get("_error", "no bets"))
                return

            for bet in bets[:1]:
                mp = bet.get("mp", 0)
                tp = bet.get("tp", 0)
                if tp > 1: tp /= 100
                if mp > 1: mp /= 100
                bet["mp"] = mp; bet["tp"] = tp

                amount, reason = self.risk.calculate_bet(balance, bet)
                if amount <= 0:
                    log.info(f"Risk blocked: {bet.get('slug')} - {reason}")
                    log_event("scan", bet.get("slug", "?"), f"blocked: {reason}")
                    continue

                slug = bet.get("slug", "")
                side = bet.get("side", "NO")
                log.info(f"Placing bet: {slug} {side} ${amount} @ {mp}")

                success = self.executor.place_bet(slug, side, amount, mp)
                if success:
                    self.risk.record_spend(amount)
                    save_trade(slug, side, "BUY", amount, mp,
                               bet.get("conf","medium"), tp,
                               bet.get("settle",""), bet.get("reason",""), response[:1000])
                    log_event("buy", slug, f"${amount} {side} mp={mp} tp={tp} | {bet.get('reason','')[:80]}")
                else:
                    log_event("error", slug, "order failed")

        except Exception as e:
            log.exception(f"Discovery error: {e}")
            log_event("error", "discovery", str(e))

    def check_positions(self):
        try:
            positions = self.executor.get_positions()
            alerts = self.monitor.evaluate_all(positions)
            if not alerts: return

            for alert in alerts:
                slug = alert["market_slug"]
                action = alert["action"]
                log.info(f"Alert: {slug} | {action} | {alert['reason']}")

                if action.startswith("SELL_"):
                    pct = int(action.split("_")[1].replace("PCT",""))
                    # Partial sell would need more complex logic, for now full sell
                    self.executor.close_position(slug)
                    log_event("sell", slug, f"gradient take profit {alert['reason']}")

                elif action == "AI_REVIEW":
                    prompt = REVIEW_PROMPT.format(
                        market_slug=slug, side=alert["side"],
                        buy_price=alert["avg_price"], current_price=alert["current_price"],
                        profit_pct=alert["pct_change"], days_held=0,
                        trigger_reason=alert["reason"])

                    log.info(f"AI review for {slug}...")
                    resp = self.claude.run(prompt, timeout_minutes=15)
                    if not resp:
                        self.monitor.record_review(slug, "hold", alert["pct_change"])
                        continue

                    result = ClaudeResearch.extract_json(resp)
                    act = result.get("action", "hold")
                    self.monitor.record_review(slug, act, alert["pct_change"])

                    if act == "sell":
                        self.executor.close_position(slug)
                        log_event("sell", slug, f"AI review: {result.get('reason','')}")
                    elif act == "add":
                        balance = self.executor.get_balance()
                        amt, _ = self.risk.calculate_bet(balance, {"mp": alert["current_price"], "tp": result.get("tp",0.1), "conf": "low"})
                        if amt > 0:
                            self.executor.place_bet(slug, alert["side"], amt, alert["current_price"])
                            self.risk.record_spend(amt)
                            log_event("add", slug, f"${amt}")
                    else:
                        log_event("hold", slug, f"AI: {result.get('reason','')}")

        except Exception as e:
            log.exception(f"Monitor error: {e}")

    def run(self):
        log.info("Bot v2 starting — Claude Research Single Engine")
        log.info(f"  Scan: {SCAN_HOURS}h | Monitor: {MONITOR_MIN}min | Phase: {get_current_phase()}")

        from modules.dashboard import create_app, set_bot
        set_bot(self)
        app = create_app()
        threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5050, debug=False), daemon=True).start()
        log.info("Dashboard: http://localhost:5050")

        # 不自动跑第一轮，等从Dashboard手动触发
        log.info("Waiting for manual trigger from Dashboard...")

        last_scan = time.time()
        last_monitor = time.time()
        last_phase = time.time()

        while True:
            now = time.time()
            if now - last_scan >= SCAN_HOURS * 3600:
                self.discover()
                last_scan = now
            if now - last_monitor >= MONITOR_MIN * 60:
                self.check_positions()
                last_monitor = now
            if now - last_phase >= 86400:
                daily_phase_check()
                last_phase = now
            time.sleep(30)

if __name__ == "__main__":
    TradingBot().run()
