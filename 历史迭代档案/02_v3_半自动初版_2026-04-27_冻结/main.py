#!/usr/bin/env python3
"""Polymarket Semi-Auto v3"""
import threading
import logging
from modules.db import init_db
from modules.monitor import PositionMonitor
from modules.dashboard import create_app, set_monitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()])
log = logging.getLogger("main")

if __name__ == "__main__":
    init_db()
    monitor = PositionMonitor()
    set_monitor(monitor)
    app = create_app()
    log.info("=== Polymarket Semi-Auto v3 ===")
    log.info("Dashboard: http://localhost:5050")
    log.info("Monitor: every 3 min | TP: +100%/+300%/+500% | SL: -50%")
    threading.Thread(target=monitor.run_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5050, debug=False)
