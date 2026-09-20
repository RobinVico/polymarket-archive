---
name: three-account-report-2026-08-27
description: 三账户对照报告(PDF)怎么生成 + 报告口径铁律「以资产真相为准, 台账会骗人」
metadata:
  type: project
---

**三账户报告** (`三账户报告-<日期>.pdf`) 的生成链, 2026-08-27 建立:

- 生成器 `scripts/gen_3acct_report.py` (只读, 新独立文件)。`from gen_run_report import CSS, money, pct, cls, label`
  复用同一套打印级设计 (跟 [[run-diagnostic-report-generator]] 同源); 冷门 slug 用本地 `LOCAL_LABELS` 补中文。
  读 `v4.db` 的 portfolio/bench/shadow_snapshot + closed_positions + bench_positions + shadow_positions
  + 实时 `/api/auto/holdings` → `report_3acct.html` → 无头 Chrome 打印 PDF (命令同 run report)。3 页。
- 曲线用**内联 SVG** 自己画 (不依赖 Chart.js): x 轴按 `collapse_gaps()` 把 >6h 的停机空档折叠掉,
  y 轴统一换算成「相对净投入的收益率 %」—— 三个账户本金不同 ($99.66/$90.47/$50), 只有 % 可比。

**口径铁律 (最重要的一条):** 战绩**以资产真相为准 = 现在总资产 − 净投入**, 逐笔平仓台账只作明细。
**Why:** 两类亏损永远不进台账 —— ① 主账户归零后卖不掉的废仓 (见 [[stuck-unsellable-positions-2026-08-27]]),
② bench 的 `vanished` 仓 (2026-08-27 时 28 个/$46.98)。所以首页"已实现盈亏"磁贴系统性偏乐观:
台账写 +$7.60, 资产口径只有 +$0.56。
**How to apply:** 以后做任何战绩汇报, 先跑 `deposits()` 那套出入金识别拿净投入, 别直接 SUM(realized_pnl_usd)。

**7-8月结论 (数据快照):** 同一批 GLM 推荐, 唯一变量是出场规则 → 主账户 +0.6% / Bench −37.9% / Shadow −34.6%。
**赚钱的不是选品, 是止盈止损。** 另: GLM 在**推荐价 ≤$0.30 区间 12 投 0 中 (0%)**, 0.50–0.70 才是主场 (76%) ——
Shadow 整套策略 (专挑 ≤$0.40) 建在了 AI 最不准的价格带上, [[shadow-third-account-2026-07-24]] 的 −60% 止损调参救不了。
