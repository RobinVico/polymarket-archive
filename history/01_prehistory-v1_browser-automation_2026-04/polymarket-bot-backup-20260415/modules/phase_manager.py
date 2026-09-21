import logging
from modules.db import get_stats, get_current_phase, set_phase

log = logging.getLogger("phase")

def daily_phase_check():
    current = get_current_phase()
    stats = get_stats(days=30)
    if not stats: return

    new = current
    if current == "phase1":
        if stats["days"] >= 30 and stats["trades"] >= 30 and stats["win_rate"] > 0.55:
            new = "phase2"
    elif current == "phase2":
        if stats.get("consec_loss_days", 0) >= 7:
            new = "phase1"
        elif stats["total_pnl"] > 100:
            new = "phase3"
    elif current == "phase3":
        if stats.get("max_drawdown", 0) >= 0.40:
            new = "phase2"
        elif stats["total_pnl"] > 500:
            new = "phase4"
    elif current == "phase4":
        if stats.get("max_drawdown", 0) >= 0.30:
            new = "phase3"

    if new != current:
        log.info(f"Phase change: {current} -> {new}")
        set_phase(new)
