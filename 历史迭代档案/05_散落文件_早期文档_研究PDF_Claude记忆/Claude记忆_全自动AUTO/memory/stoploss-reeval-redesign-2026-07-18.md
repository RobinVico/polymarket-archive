---
name: stoploss-reeval-redesign-2026-07-18
description: 止损/重评大改(用户2026-07-18); 收敛&混合砸穿直接平仓; 事件-50%硬止损+盘中5pp触发重评; exit护栏删; cancel_autostop删
metadata: 
  node_type: memory
  type: project
  originSessionId: 3e9e62ad-6021-4de6-a1eb-e9c1e479904f
---

用户 2026-07-18 拍板重做止损/重评(**背景**: 事件型深亏拖着不卖是最大亏损源,见 [[dashboard-rework-monitor-2026-07-11]] 那份诊断报告)。**要点: "止损" 和 "每日重评" 是两回事** —— 每天 15:00 全仓巡检重评对**所有**仓照旧(更新 q、盈利仓往上改、也能兜底 exit),这次只改"止损"。

**新止损规则(改的是 monitor.py + auto_reeval.py, 是 AUTO 有意分叉, 同步老项目要保留):**
- **收敛型 convergent**: 从最高价回撤 20%(≤3天 12%)+ 连6拍确认 → **直接平仓**(不再交重评)。`_evaluate_position` 里 `_direct_stop = tier in ("convergent","hybrid")`。盘中不再做亏损触发重评(`_maybe_trigger` 里 `tier != "event_driven" → return`)。
- **混合型 hybrid**: 不变(回撤35%直接平仓)。
- **事件型 event_driven**:
  - 亏 **> 50% → 强行直接平仓**(`EVENT_DRIVEN_HARD_STOP_PCT=0.50`, 早于重评/护栏/手动关止损, 任何东西越不过)+ $0.05 地板兜底。(这条是先前已落地的。)
  - **盘中【任何盈亏水平】从"持有期最好点(最低 loss_pct)"回撤 ≥5pp → 触发 1 次重评**。基线=上次触发后见过的最低 loss_pct(涨回去就下移); loss≥基线+5pp 触发并把基线重置到当前 → **单次暴跌只算1次**(不按5pp整除)。**无时间冷却**(去掉了老的 6h)。40%→涨回35%→再跌40% 会再触发。实现在 `monitor._maybe_trigger_auto_reeval`,用 `get/set_reeval_watch_loss` 存基线; env `AUTO_REEVAL_RETRIGGER_DROP` 默认从 0.10 改成 **0.05**。
- **exit 护栏 `guard_event_driven_exit` 已删**(先前就没被调用了,只剩死 def)→ 重评说 exit 就立刻卖。
- **`cancel_autostop` 删掉**: 从重评 prompt/schema 移除(两个模型都不再被告知这个选项); 执行处 `_auto_execute` 中和为 no-op(即使模型返回也按 hold, 不关止损)。**手动"止损OFF"开关先留着**(用户没要求删)。

**注意**: 事件型"任何水平5pp就触发重评"会比较费 API(13个事件仓+价格波动)——用户明知,是他要的。`PENDING_REEVAL` 状态实际已退役(所有止损都直接平仓了)。

关联: [[kelly-bankroll-freeze-2026-07-11]] [[pipeline-steps34-live-2026-07-08]]
