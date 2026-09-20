"""AUTO 流水线 第2.5步: 24小时全仓巡检重评 (用户 2026-07-08 定)。

跟"大跌触发"的 auto-reeval 相互独立: 这个是**定时体检** —— 每天 AUTO_DAILY_REEVAL_HOUR 点
(默认 10:00 本机时间) 把**所有持仓**逐个交给现有 auto_reeval.run_and_store:
- 走重评专用 key (ZHIPUAI_API_KEY_REEVAL → autobot 映射给 ZHIPUAI_API_KEY), 不碰选品 key。
- force_manual=False, 语义跟大跌触发完全一致: 离线 → 决策自动执行 (动真钱); 在线 → 挂 pending 等确认。
- 唯一 skip: 该仓已有进行中的重评 (inflight) → 不重复起。盈利仓/止损OFF仓照样体检 (用户: 所有仓位)。
- 首次部署"上膛不开火": marker 为空时只记 slot 不补跑, 从明天起每天准点跑 (防止部署当天突然全仓重评)。
- 大跌触发那条路不受影响, 照常工作; 两边共用 inflight 锁天然互斥。
"""
import os
import time
import logging
from datetime import datetime, timedelta

log = logging.getLogger("auto_daily_reeval")

DAILY_HOUR = int(os.environ.get("AUTO_DAILY_REEVAL_HOUR", "15"))   # 每天几点跑 (本机时间; 用户 2026-07-09 拍板: 10点→15点)
_STATE_KEY = "auto_daily_reeval_last_slot"


def _current_slot(now=None):
    """今天已过 DAILY_HOUR → 'YYYY-MM-DD'; 还没到 → 昨天的日期 (归属昨天的 slot)。"""
    now = now or datetime.now()
    d = now.date() if now.hour >= DAILY_HOUR else (now - timedelta(days=1)).date()
    return d.strftime("%Y-%m-%d")


def maybe_run():
    """由 auto_scheduler 心跳每分钟调一次: 到点且没跑过 → 跑全仓巡检。"""
    from modules.db import get_app_state, set_app_state
    # 2026-09-01 用户令「关闭 API 部分」: 官方的「API 紧急暂停」开关原本只挡住 monitor 的盘中触发,
    # 挡不住这条每日巡检 (run_and_store 入口没查) → 补上, 让那个开关名副其实。
    try:
        from modules.db import get_api_paused
        if get_api_paused():
            return
    except Exception:
        pass
    slot = _current_slot()
    marker = get_app_state(_STATE_KEY)
    if marker == slot:
        return
    if marker is None:
        set_app_state(_STATE_KEY, slot)
        log.info(f"[daily-reeval] 已上膛: 从下一个 {DAILY_HOUR}:00 起每天全仓巡检重评 (今天不补跑)")
        return
    # 用户 2026-07-09 把点位 10:00→15:00: 改点当天 marker(今天已评过) 会比新口径 slot(还没到点=昨天) 更新 —
    # 只有 slot 真正"新于" marker 才触发 (ISO 日期字符串可直接比大小), 防改点当天误跑/双跑。
    if slot <= marker:
        return
    set_app_state(_STATE_KEY, slot)
    log.info(f"[daily-reeval] 触发 slot={slot}")
    try:
        run_sweep(slot)
    except Exception:
        log.exception("[daily-reeval] 巡检异常 (等明天的 slot)")


# 用户 2026-07-10 拍板: 串行太慢 (agent 深搜单仓 6~64 分钟, 8 仓拖了 3 小时) →
# 学选品的多路并发: N 路工作队列, 一个评完下一个立刻顶上。env 可调, 默认 4。
CONCURRENCY = int(os.environ.get("AUTO_DAILY_REEVAL_CONCURRENCY", "4"))


def run_sweep(slot):
    """全仓巡检: CONCURRENCY 路并发调现有重评 (工作队列, 一个评完下一个立刻顶上;
    用户 2026-07-10 拍板, 替代原先的逐仓串行)。"""
    from modules import auto_reeval
    if not auto_reeval.is_enabled():
        log.info("[daily-reeval] 重评未启用 (缺 ZHIPUAI_API_KEY_REEVAL / ANTHROPIC_API_KEY), 跳过")
        return
    from modules.executor import Executor
    from modules.db import get_position_meta, has_inflight_auto_reeval, save_auto_reeval_pending
    positions = Executor.get().get_positions() or []
    if not positions:
        log.info("[daily-reeval] 当前无持仓, 无需巡检")
        return
    t0 = time.time()

    def _one(pos):
        token_id = pos.get("asset")
        if not token_id:
            return "skip"
        try:
            if has_inflight_auto_reeval(token_id):
                log.info(f"[daily-reeval] 跳过 (已有进行中重评): {(pos.get('title') or '')[:40]}")
                return "skip"
            meta = get_position_meta(token_id) or {}
            avg = float(pos.get("avg_price") or meta.get("entry_price") or 0)
            cur = float(pos.get("cur_price") or 0)
            loss_pct = (avg - cur) / avg if avg > 0 else 0.0
            sug_id = save_auto_reeval_pending(token_id, pos, meta, loss_pct, cur, avg)
            log.info(f"[daily-reeval] 巡检 {(pos.get('title') or '')[:40]} "
                     f"(盈亏 {-loss_pct*100:+.0f}%, id={sug_id}) …")
            auto_reeval.run_and_store(sug_id, pos, meta)   # force_manual=False: 离线自动执行/在线挂 pending
            return "done"
        except Exception:
            log.exception(f"[daily-reeval] 单仓巡检失败: {(pos.get('title') or '')[:40]} (不影响其他仓)")
            return "fail"

    from concurrent.futures import ThreadPoolExecutor, as_completed
    conc = max(1, CONCURRENCY)
    log.info(f"[daily-reeval] 开始全仓巡检: {len(positions)} 个持仓, {conc} 路并发 (一个评完下一个顶上)")
    results = []
    with ThreadPoolExecutor(max_workers=conc) as pool:
        futs = [pool.submit(_one, p) for p in positions]
        for f in as_completed(futs):
            try:
                results.append(f.result())
            except Exception:
                results.append("fail")
                log.exception("[daily-reeval] 巡检线程异常")
    done, skipped, failed = results.count("done"), results.count("skip"), results.count("fail")
    log.info(f"[daily-reeval] 巡检完成: 评了 {done}, 跳过 {skipped}, 失败 {failed}, 耗时 {time.time()-t0:.0f}s")


def register_routes(app):
    from flask import jsonify
    import threading

    @app.route("/api/auto/reeval_sweep_now", methods=["POST"])
    def reeval_sweep_now():
        """手动触发一轮全仓巡检 (测试用), 不动 slot 标记。"""
        slot = "manual-" + datetime.now().strftime("%m%d-%H%M%S")
        threading.Thread(target=run_sweep, args=(slot,), daemon=True).start()
        return jsonify({"ok": True, "slot": slot, "message": "巡检已在后台开跑, 看 bot.log / 主页重评卡"})
