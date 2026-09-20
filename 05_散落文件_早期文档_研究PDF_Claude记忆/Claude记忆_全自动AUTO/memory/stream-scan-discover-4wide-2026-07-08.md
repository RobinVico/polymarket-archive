---
name: stream-scan-discover-4wide-2026-07-08
description: "AUTO 定时链路改为\"扫一个喂一个\"4路并发流式管道 + 有推荐就立马下单(消费线程); 附智谱并发实测"
metadata: 
  node_type: memory
  type: project
  originSessionId: a0d2515c-e088-4b44-b8d1-9cbcafa39b11
---

用户 2026-07-08 拍板并已落地: 全自动定时链路(09:00/21:00)从「先 `scan_all_tags` 全扫 → 再串行逐个 GLM 选品」改成 **流式"扫一个喂一个" 4 路并发** —— 每个 tag 丢给 GLM 前**当场重扫**(拿最新盘口), 排在后面的类别不再吃十几分钟前的旧数据。

**实现**: `modules/auto_discovery.py` 新增 `scan_and_discover_stream()` / `_scan_and_discover_stream_locked()` / `_stream_process_tag()` / `_count_candidates_in_report()`; `auto_scheduler._run_scan` 改为调 `scan_and_discover_stream`(替掉 scan_all_tags + run_for_slot 两段)。**scanner.py 未改**(只调用它的 `scan_by_tag` + `_slugify_tag`/`_update_manifest_entry`/`_write_manifest_atomic`)。并发数 env `AUTO_DISCOVERY_CONCURRENCY` 默认 4。4 路 GLM 走 `_run_tag_locked`(不抢锁), 整轮由顶层持一次 `_disc_lock` 互斥。手动 `discover_now` 仍走老 `run_for_slot`(读缓存报告, 不变)。

**即时下单 (用户 2026-07-09 加, 已落地)**: "有推荐就立马下单, 其他 tag 继续分析"。用**生产者-消费者**: 分析 4 路只管产候选写库; `auto_trader.run_execution_consumer(slot, stop_event, poll_s=3)` 一个独立消费线程每 3s 轮询, 一有 'new' 候选就立刻 `execute_for_slot` 下单。下单**全程串行**(复用现成 `_run_lock` + 宇宙闸/漂移复核/防对锁/台账/录档案全部安全逻辑, **真钱路径一字未改**), 分析线程从不因下单阻塞。`auto_scheduler._run_scan` 起这个线程 → 跑 scan_and_discover_stream → set stop_event + join → 收尾再 execute_for_slot 兜一次(消费线程若启动失败, 收尾这次就退回等价老的批量执行)。防双买靠"执行即把候选标非'new'"(不只靠锁)。实测(mock)证实"首次下单时只完成 8/14 tag 分析"= 真边分析边下单, 且无双买/无残留。

**为什么并发=4**: scratchpad 实测该 discovery 账户(key 尾4=TX1M): ① **没有 1302 硬并发墙**(廉价 2~13、重调用 8/12 都没冒 1302); ② 限流**按账户**算(同账户多把 key 无用, 想提并发只能升等级或换独立账户); ③ 重调用(search_pro+思考max)并发 >~4 开始**丢连接**(不是拒绝, 是负载甩连接), 生产 600s+默认重试能兜住 → 4 是可靠甜区。智谱按量付费=用户权益 V0-V3(积分=消费, 1元≈1积分, 近3月最高定档), 确切并发数官方不公开、只在控制台看。

**Why**: 用户要 GLM 看到实时数据 + 并行提速。medium 中范围候选多、够门槛(≥5)类别会多, 收益实打实(用户明确: 老的 0~1 眼见少是因为当时用标准扫描)。
**How to apply**: 同步老项目 scanner.py 时这套不受影响(没改它, 但用了它几个下划线助手, 若老项目改名需跟改调用处); 调并发改 env `AUTO_DISCOVERY_CONCURRENCY`; 消费线程轮询间隔在 `run_execution_consumer` 的 `poll_s` 默认 3s。⚠️ 两处改动(4路流式选品 + 即时下单)截至 2026-07-09 00:20 只跑了 **mock 单测/集成测 + 干净重启, 真实 GLM+真钱 live 尚未跑过**; 首次真跑 = 2026-07-09 **09:00 那趟**(它会真扫+真 GLM 4 路+真下单)。真钱下单逻辑本身没改, 风险面只在"流式产候选 + 消费线程调度"这层。关联 [[pipeline-steps34-live-2026-07-08]]。
