---
name: run-diagnostic-report-generator
description: 运行诊断报告(PDF)怎么生成/更新 —— scripts/gen_run_report.py → report.html → 无头Chrome打印PDF
metadata: 
  node_type: memory
  type: project
  originSessionId: 4aac8019-2146-466d-b53c-76ecb9e2c9d4
---

**运行诊断报告** (`运行诊断报告-<日期>.pdf`, 给用户看账户运行体检的那份 PDF) 的生成链，2026-07-20 建立可复现来源:

- 生成器 = `scripts/gen_run_report.py` (只读; 新独立文件, 不碰同步模块)。读**实时** `http://127.0.0.1:5052/api/auto/holdings` (现金/持仓/浮盈, 权威源; ⚠️ 它的 `pnl_pct` 是坏的×100, 用 `(cur-avg)/avg` 自己算价格收益) + `v4.db` 的 `closed_positions`(带 `stop_loss_tier`=仓位类型/止损档) 和 `auto_reeval_suggestions`(深水扛单统计) → 吐自包含 `report.html`。
- PDF = 无头 Chrome 打印: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="运行诊断报告-<日期>.pdf" "file://.../report.html"`。(旧 07-18 版 PDF 元数据 Producer=Skia/PDF+Creator=HeadlessChrome+Title=report.html 就是这么来的, 但当时源 html 没存 → 本脚本补上。)
- 视觉 QA: `brew install poppler` 后 `pdftoppm -png -r 96 xxx.pdf pg` 渲染每页, 再 Read 看。A4 打印区 ~718px, 生成器 CSS 已按此调; 35 行平仓表压密度(`table.closed` padding 3.8px)刚好一页; 章节用 `section.break`{break-before} 控分页, 大表 `break-inside:auto`。
- 报告结构: KPI卡(总资产/现金/持仓/浮动/已实现, 带 vs 上版 delta) → 头条「新策略 vs 以前」before/after表+Claude Opus铁证 → ①②当前持仓(赚/亏, 带止损档徽章) → ③全部平仓盈亏表(**含止损档列**, 用户明确要的) → ④钱亏在哪(tier横条+平仓方式+最惨几笔) → ⑤钱赚在哪·最大几笔 → ⑥GLM深水扛单 → ⑦可以改的。
- 版本基线 `PREV` dict (上一版日期/数值) 写死在脚本顶部, 出新版报告时手动更新它算 delta。跑法: `.venv/bin/python3 scripts/gen_run_report.py 2026-07-20`。
- 这是**只读**报告, 不改任何仓位/参数; 跟 [[docs-sync-with-code]] 的策略/版本同步无关 (加报告工具不用 bump 版本)。相关: [[stoploss-reeval-redesign-2026-07-18]] (报告的主线故事=这套止损改造起效)。

**第二个生成器 `scripts/gen_loss_report.py`** (2026-07-23 建, 大亏损专项复盘): `from gen_run_report import CSS,money,pct,cls,tier_badge,label,classify_exit` **复用同一套设计** (导入安全, gen_run_report 无 import 副作用)。聚焦某轮回撤: 逐笔割肉/止盈全字段明细(标签/入场价/股数/平仓方式/**事件原因**人工标注 WHY dict) + 亏损拆解(**回撤=割肉净额+浮盈回吐**, 回吐=峰值→现在 减 已实现) + 改进策略。峰值 `PEAK` + 起点 `SINCE` 写死在顶部。出 `report_loss.html` → 同样无头Chrome打印 `亏损复盘报告-<日期>.pdf`。以后要复盘别轮亏损, 改 PEAK/SINCE/WHY 重跑。⚠️ 冷门盘 slug 通用 LABELS 覆盖不到 → 脚本内 `LOSS_LABELS`+`llabel` 补中文标签。
