"""AUTO 流水线 第1步: 定时扫描 (用户 2026-07-08 定: 每天早 9:00 / 晚 21:00 本机时间自动全扫)。

只读安全: 只拉 Polymarket 公开行情写扫描报告 (data/scan_reports/), 不调 LLM、不下单、不碰钱。
独立文件不改 monitor.py —— 保证以后从半自动老项目同步策略代码时零冲突 (autobot.py 里启动)。

设计:
- 每 60s 看一次钟。slot = 最近一个已到点的扫描时刻 (09:00 / 21:00)。
- app_state['auto_scan_last_slot'] 记录上次已跑的 slot: 重启不重放, 停机错过的 slot 开机补跑
  (例: 08:50 停机 09:10 开机 → 补跑 09:00 那趟; 已跑过则跳过)。
- 扫描失败也记 marker (本 slot 不重试, 等下一个 slot), 防止对 API 连环重放。
"""
import threading
import time
import logging
from datetime import datetime, timedelta

log = logging.getLogger("auto_scheduler")

SCAN_HOURS = (9, 21)        # 本机时间整点; 用户定, 改这里即可
CHECK_EVERY_SEC = 60
_STATE_KEY = "auto_scan_last_slot"


def _current_slot(now=None):
    """返回当前所属 slot 标识 'YYYY-MM-DD HH:00' = 最近一个已到点的扫描时刻;
    今天还没到第一个点 → 归属昨天最后一个 slot。"""
    now = now or datetime.now()
    hours = sorted(SCAN_HOURS)
    todays = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in hours]
    passed = [t for t in todays if t <= now]
    if passed:
        return passed[-1].strftime("%Y-%m-%d %H:00")
    y = (now - timedelta(days=1)).replace(hour=hours[-1], minute=0, second=0, microsecond=0)
    return y.strftime("%Y-%m-%d %H:00")


def _run_scan(slot):
    t0 = time.time()
    # 用户 2026-07-08/09 拍板: 全自动链路 **只用中范围扫描** + **流式"扫一个喂一个"多路并发** +
    #   **有推荐就立马下单**:
    #   ① 第1步(扫)+第2步(选品) 合并进 auto_discovery.scan_and_discover_stream —— 每个 tag 丢 GLM
    #      前当场重扫拿最新盘口, 排在后面的类别也不吃旧数据; 4 路并行只管产候选写库。
    #   ② 第3+4步(下单) 由 auto_trader.run_execution_consumer 一个独立消费线程即时消化 —— 一发现
    #      有新候选就立刻执行 (串行下单, 复用全部安全逻辑), 分析线程从不因下单而阻塞。
    #   medium/并发数/门槛 都在 auto_discovery 写死或 env 可调; 手动页面扫描不受影响, 别改回 standard。
    log.info("[auto-scan] 开始流式扫描+选品+即时下单 (tier 1+2, medium, 扫一个喂一个多路并发; 有推荐就立马下单)")
    stop_exec = threading.Event()
    consumer = None
    try:
        from modules.auto_trader import run_execution_consumer
        consumer = threading.Thread(target=run_execution_consumer, args=(slot, stop_exec),
                                    daemon=True, name="stream-exec-consumer")
        consumer.start()
    except Exception:
        log.exception("[auto-scan] 执行消费线程启动失败 (退回收尾统一执行)")
    try:
        from modules.auto_discovery import scan_and_discover_stream
        scan_and_discover_stream(slot)
    except Exception:
        log.exception("[auto-scan] 流式扫描+选品异常 (不影响下一个 slot)")
    finally:
        stop_exec.set()
        if consumer is not None:
            consumer.join(timeout=180)
    # 收尾兜底: 把最后可能没执行到的候选再统一扫一遍 (幂等 —— 已执行的都标非'new' 不会重复下单;
    # 消费线程若启动失败, 这里就是唯一的执行入口, 等价老的批量执行)。
    try:
        from modules.auto_trader import execute_for_slot
        execute_for_slot(slot)
    except Exception:
        log.exception("[auto-scan] 收尾执行异常 (不影响下一个 slot)")
    log.info(f"[auto-scan] 本轮完成 (扫+选+执行一条龙), 耗时 {time.time() - t0:.0f}s")


def _loop():
    from modules.db import get_app_state, set_app_state
    log.info(f"[auto-scan] 定时扫描调度器已启动: 每天 {'/'.join(str(h)+':00' for h in sorted(SCAN_HOURS))} (本机时间)")
    while True:
        try:
            slot = _current_slot()
            if get_app_state(_STATE_KEY) != slot:
                set_app_state(_STATE_KEY, slot)
                log.info(f"[auto-scan] 触发 slot={slot}")
                try:
                    _run_scan(slot)
                except Exception:
                    log.exception("[auto-scan] 本轮扫描失败 (本 slot 不重试, 等下一个 slot)")
        except Exception:
            log.exception("[auto-scan] 调度循环异常")
        # 第2.5步: 24h 全仓巡检重评 (自己管 slot 标记, 到点才真跑)
        try:
            from modules.auto_daily_reeval import maybe_run
            maybe_run()
        except Exception:
            log.exception("[daily-reeval] 调度检查异常")
        time.sleep(CHECK_EVERY_SEC)


def start_scheduler():
    threading.Thread(target=_loop, daemon=True, name="auto-scan-scheduler").start()
