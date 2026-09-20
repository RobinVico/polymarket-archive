import logging
from modules.db import get_daily_spend, add_daily_spend, get_current_phase
from datetime import datetime

log = logging.getLogger("risk")

PHASES = {
    "phase1": {"daily_max": 5.00,  "bet_min": 0.50, "bet_max": 1.00},
    "phase2": {"daily_max": 15.00, "bet_min": 1.00, "bet_max": 5.00},
    "phase3": {"daily_max": 50.00, "bet_min": 3.00, "bet_max": 15.00},
    "phase4": {"daily_max": 200.00,"bet_min": 5.00, "bet_max": 50.00},
}

KELLY_FRACTION = {"high": 1/8, "medium": 1/10, "low": 1/15}

class RiskEngine:
    def __init__(self):
        self._last_date = datetime.now().strftime("%Y-%m-%d")

    def calculate_bet(self, balance, bet):
        mp = bet.get("mp", 0)
        tp = bet.get("tp", 0)
        conf = bet.get("conf", "medium")
        phase = get_current_phase()
        cfg = PHASES.get(phase, PHASES["phase1"])

        if mp <= 0 or tp <= 0:
            return 0, "invalid prices"
        if tp / mp < 2.5:
            return 0, f"edge too small: tp/mp={tp/mp:.2f}"

        b = (1 - mp) / mp
        kelly = (b * tp - (1 - tp)) / b
        if kelly <= 0:
            return 0, f"negative kelly: {kelly:.4f}"

        frac = KELLY_FRACTION.get(conf, 1/10)
        amount = kelly * frac * balance
        amount = max(cfg["bet_min"], min(cfg["bet_max"], amount))
        amount = min(amount, balance * 0.10)

        # Daily budget
        today = datetime.now().strftime("%Y-%m-%d")
        spent = get_daily_spend(today)
        remaining = cfg["daily_max"] - spent
        if remaining < cfg["bet_min"]:
            return 0, "daily budget exhausted"
        amount = min(amount, remaining)

        if amount < cfg["bet_min"]:
            return 0, f"amount {amount:.2f} < min {cfg['bet_min']}"

        amount = round(amount, 2)
        log.info(f"Risk: kelly={kelly:.4f} frac={frac} -> ${amount} (phase={phase}, balance=${balance:.2f})")
        return amount, "ok"

    def record_spend(self, amount):
        add_daily_spend(amount)
