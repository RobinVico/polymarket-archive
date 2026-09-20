---
name: strategy-ppt-generator
description: 策略总览企业 PPT (可打印) 交付物 + 生成器脚本位置; 版本升级后要核对内容再重新生成
metadata: 
  node_type: memory
  type: project
  originSessionId: b7b44668-8c8f-44bc-860c-c2d79afe6b3c
---

用户 2026-07-06 要求: 改动太多太乱, 要一份**企业风格、可打印的 PPT** 讲清现行状况 —— 出场策略/重评策略/新仓金额范围/找仓规则/钱相关信息, 每个主题 1–2 页。

**交付**: `Polymarket_Bot_策略总览_v{VERSION}.pptx` (项目根目录, 16:9, 16 页; 文件名带版本号, 升版本会生成新文件、删旧的)。**当前 = v7.4.5** (2026-07-08 更新: **混合型砸穿止损→直接平仓不走重评, 只事件型+收敛型走 API 重评[7.4.5]**; 2026-07-06: 止盈加"事件型翻倍先到全卖/0.92卖半+后半0.78保护"; 止损 事件型 无→60%、混合型改从最高价回撤35%移动止损、未分类默认当混合删-25%老仓档; 测试仓slide加往期+最高点+统计)。⚠️ **分享版生成器 `gen_strategy_ppt_share.py` 也含同套策略内容, 现已过时(还停在旧出场规则), 用户要分享前需同步更新+重生成**。P12 = 入场 edge 门槛 (prompts.py §推荐门槛 v7.2: 基础 6/8/10pp ± 价位叠加 ∓3/1pp, 地板 5pp, 用户看完决定不改)。
**分享版 (2026-07-07 加)**: `Polymarket_Bot_项目分享_v{VERSION}.pptx` + 生成器 `scripts/gen_strategy_ppt_share.py` — 给熟人看: 数据不脱敏, 语气"你"→中性; 比内部版 +5 页 (P3 项目是什么 / P4 真实战绩含 bot.log 实弹记录 / P17 版本演进 / P18 踩坑与诚实现状 / P19 开源结尾), −1 页 (参数速查表); 战绩数字从 /api/history/analytics + bot.log 现拉, 重生成时要更新。
**生成器**: `scripts/gen_strategy_ppt.py` (VERSION 常量在顶部, 改它文件名自动跟着变)。**跑法**: python-pptx 装在 `/tmp/pptenv` (`/tmp/pptenv/bin/python3 scripts/gen_strategy_ppt.py`; 没了就 `python3 -m venv /tmp/pptenv && /tmp/pptenv/bin/pip install python-pptx`)。项目 .venv / polymarket-bot .venv 都没装 pptx。
**验证**: 抽正文核对新内容进没进 —— ⚠️ **表格内容在 `shape.table` 不在 `shape.text_frame`**, 抽取要同时读 `has_table` 的单元格 (漏了会假报"内容没进")。

**How to apply:**
- 内容是**手工从代码核对的快照** (monitor.py 常量 / auto_reeval.py / sizing.py / scanner FILTERS / 实时持仓举例)。以后大版本升级或阈值改了 → 先核对更新脚本内容 + 封面快照数字 + VERSION/DATE, 再重新生成。
- 排版 QA 用 Keynote AppleScript 转 PDF 再 Read 目检 (无 soffice)。
- 风格遵守 [[plain-language-explanations]]: 大白话 + 真实仓位举例 (SpaceX/霍尔木兹/MBS/Wesley Bell), 每页表格+要点, 不甩术语。
