---
name: docs-sync-all-on-change
description: "铁律 — 改任何策略/代码/版本后必须当次同步全部文档 + 两个 PPT(内部+分享版), 一个都不能漏"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 80767cb3-3d97-4b57-bdf2-c73b9ce18408
---

用户 2026-07-08 强调"一定要写死": **改任何策略/代码/版本后, 所有文档必须当次全部同步更新, 一个都不能漏, 别攒着**。起因 = 分享版 PPT 停在旧版差点漏掉(之前 monitor 启动日志、公开库 README 标题也各漏过)。

**Why:** 用户会拿这些给别人看 / 自己复盘; 任何一处过时 = 等于撒谎/尴尬。

**How to apply — 改完当次跑一遍清单(完整版在 CLAUDE.md「📌 文档/PPT 同步铁律」):**
1. `modules/version.py` VERSION(单一来源, 决定所有页面+文件名版本号)
2. `main.py` 启动日志那行策略描述
3. `modules/dashboard.py` UI(持仓 tier 下拉 title / 规则展示卡)
4. `CLAUDE.md` 变更日志 + 相关设计段
5. `技术报告.md` + `TECHNICAL_REPORT.md`(中英都改, 见 [[docs-i18n-parity]])
6. `README.zh.md` + `README.md`(「当前版本概要」版本号 + 策略 ASCII 块 + 版本摘要行)
7. `SECURITY.zh.md` + `SECURITY.md`(仅版本/安全相关时)
8. 内部 PPT: `scripts/gen_strategy_ppt.py` → 重生成 → 删旧 pptx
9. **分享版 PPT: `scripts/gen_strategy_ppt_share.py` → 重生成 → 删旧** ← 最易漏, 独立文件但同套策略内容
10. 相关 memory([[strategy-ppt-generator]] / [[auto-reeval-pending-changes]] 等)

PPT 跑法: `/tmp/pptenv/bin/python3 scripts/gen_strategy_ppt*.py`(python-pptx 装在 /tmp/pptenv)。
验证: 抽 PPT 正文核对(含表格 `shape.table` 单元格, 别只读 text_frame)+ grep 旧值无残留。
