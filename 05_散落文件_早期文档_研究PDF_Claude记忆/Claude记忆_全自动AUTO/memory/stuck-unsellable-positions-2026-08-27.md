---
name: stuck-unsellable-positions-2026-08-27
description: 卖不掉的仓 (无订单簿) 会让 monitor 每30s重试一次、永不停止; monitor.py 按隔离铁律不能改
metadata:
  type: project
---

2026-08-27 停机 16 天后重启, 发现主账户有 **6 个仓卡在无限重试卖出**: 触发止损/止盈 → `sell` 报
`404 No orderbook exists for the requested token id` → 失败 → 下一拍 (30s) 原样再来。24 次 AUTO_SELL 只成功 3 次。
典型是价格已归零 ($0.000 跌破 $0.05 地板) 或市场已关闭/结算的仓。

**Why:** 不亏钱, 但每 30s 白打一轮 CLOB 请求 + 日志被刷屏, 且这些仓会永远挂在持仓面板上不消失。
`auto_bench.py` 早就有解法 —— `_sell_skip_until` 卖失败退避 10 分钟 + 「尘埃仓强关 (剩余<$0.05 卖不动)」
直接标平仓; 但主链路的 `monitor.py` 是**从老项目同步来的模块**, 按隔离铁律不能改 (见 [[项目 CLAUDE.md 开发协议]]),
所以这个坑在主账户一直存在。

**How to apply:** 用户哪天嫌烦要修, 别直接改 monitor.py —— 照 AUTO 惯例开独立新文件 (`modules/auto_*.py`)
做退避/尘埃仓强关, 或走 env 旋钮; 动手前先按「一步一报」问用户 (加保护属于"想加任何保护先问")。
卡住的 6 个: Bank of Korea 两个 / Kostyantynivka / Russia-Ukraine diplomatic / Gemini Pro / Iranian blockade。
