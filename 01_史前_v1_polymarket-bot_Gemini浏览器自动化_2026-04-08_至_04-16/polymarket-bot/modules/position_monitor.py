import logging
from datetime import datetime

log = logging.getLogger("monitor")

TAKE_PROFIT = [
    {"name": "tier1", "trigger_pct": 100, "sell_pct": 30},
    {"name": "tier2", "trigger_pct": 300, "sell_pct": 30},
    {"name": "tier3", "trigger_pct": 500, "sell_pct": 20},
]
STOP_LOSS_PCT = -50
TIME_REVIEW_DAYS = 7
PRICE_CHANGE_TRIGGER = 30


class PositionMonitor:
    def __init__(self):
        self.review_history = {}

    def evaluate_all(self, positions):
        alerts = []
        for pos in positions:
            avg = pos.get("avg_price", 0)
            cur = pos.get("current_price", 0)
            if avg <= 0: continue
            pct = ((cur - avg) / avg) * 100
            action, reason = self._evaluate(pos, pct)
            if action != "HOLD":
                alerts.append({**pos, "pct_change": pct, "action": action, "reason": reason})
        return alerts

    def _evaluate(self, pos, profit_pct):
        slug = pos.get("market_slug", "")

        # Stop loss
        if profit_pct <= STOP_LOSS_PCT:
            return "AI_REVIEW", f"loss {profit_pct:.0f}%"

        # Gradient take profit
        for tp in TAKE_PROFIT:
            if profit_pct >= tp["trigger_pct"]:
                sold_key = f"{tp['name']}_sold"
                if not self.review_history.get(f"{slug}_{sold_key}", False):
                    return f"SELL_{tp['sell_pct']}PCT", f"profit {profit_pct:.0f}% -> sell {tp['sell_pct']}%"

        # Price change trigger for AI review
        last = self.review_history.get(slug, {})
        last_pct = last.get("last_pct", 0)
        if abs(profit_pct - last_pct) >= PRICE_CHANGE_TRIGGER:
            return "AI_REVIEW", f"price change {abs(profit_pct - last_pct):.0f}%"

        return "HOLD", None

    def record_review(self, slug, action, pct):
        self.review_history[slug] = {"last_action": action, "last_pct": pct, "time": datetime.now().isoformat()}

    def record_tier_sold(self, slug, tier_name):
        self.review_history[f"{slug}_{tier_name}_sold"] = True
