---
name: paper-trading-feature
description: "测试仓/模拟盘 (/paper, v7.1) — 不真下单的仓位验证; 录入拿不准的 Claude 推荐, 实时盯盘跑同一套算法看准不准"
metadata: 
  node_type: memory
  type: project
  originSessionId: c0f4c148-62b8-42d7-a3a7-e47259a6349f
---

**v7.1 (2026-06-22) 模拟盘/测试仓, 阶段1 已上线** (用户要的: 把看着离谱/拿不准的 Claude 推荐丢进去, 不真下单, 按填的入场价实时盯盘, 跑跟真仓一模一样的算法, 验证 Claude 预测准不准)。

**🔒 安全铁律: 模拟仓绝不碰真实下单** —— `monitor._evaluate_paper_positions` 和所有 `/api/paper/*` 路由**永不调 `executor.sell/buy`** (只 `get_best_bid` 读价)。改这块务必守住。

落地:
- **db.py**: `paper_positions` 表 (token_id/slug/title/side/entry_price/size_usd/shares/q/tier/end_date + 跟踪 cur_price/peak_price/monitor_state + would_sell_* 首次快照 + status open/cleared/resolved + final_outcome)。CRUD: `add_paper_position`/`get_paper_positions(status)`/`get_open_paper_positions`/`clear_paper_position`/`clear_all_paper_positions`/`update_paper_tracking`/`set_paper_would_sell`(只记一次)/`resolve_paper_position`。
- **monitor.py**: `_evaluate_position` 加 `breach_store` 参数 (paper 用独立 `self._paper_trail_breach`, 不串真仓移动止损计数)。`_evaluate_paper_positions()` 每心跳: Gamma 拉持有 side 实时价 → 合成 pos/meta → 跑同一 `_evaluate_position` (dry-run, executed_action='' 让规则始终评估) → 更新 cur/peak/state → 命中硬动作记首次 would_sell (止盈用 best_bid/其余用 cur, 算模拟盈亏) → closed 且价收敛 0/1 则 resolve。**命中后继续盯到结算** (用户选)。run_loop 每心跳调一次 (wrapped)。
- **dashboard.py**: `/paper` 页面 (`PAPER_HTML` 模块级常量) + 路由 `/api/paper/{list,add,clear,clear_all}`。`add` 按 slug+side 从 Gamma 解析 token_id/标题/结算日 (因为没真持仓拿不到 token)。录入 = 手动表单 + 粘贴 Claude JSON 块一键 (entry 默认用 rec 的 cur_price, 每条统一金额)。主页 + /history nav 加「🧪 测试仓」。⚠️ `/api/paper/add` 路由要 `from modules.db import ... log_event` (踩过坑: 漏 import log_event → 500 但仓已加)。
- **list 口径**: 未结算 pnl=(cur−entry)×shares; 已结算 用 final_outcome(0/1) 当价。days_left 带 tzinfo guard。`/list` 返回 open+resolved (cleared 隐藏)。

实测: 录入 Kostyantynivka No@0.54 → 一心跳后 cur→0.786, 模拟 +$4.56(+46%), state=HOLD; 确认无真实卖出。

**✅ 阶段2 已上线 (2026-06-22) = 手动重评, 零API零钱** (用户反复强调测试仓绝不碰钱): `/api/paper/reeval_prompt` 复用 `build_reeval_prompt` + `_pre_dump_center` 反锚定 + Gamma resolution (**全只读**) 生成提示词 → 前端「📋 复制重评提示词」→ 用户**自己贴去 Claude.ai 免费重评** → 读到新 q → 该仓「存q」→ `/api/paper/update_q` (db.update_paper_q)。**绝无「🤖 API重评」按钮、绝不自动调付费 API**。`_evaluate_position` 加 `breach_store` 参数 (paper 传 `self._paper_trail_breach`)。🔒 已 grep 审计: 6 个 /api/paper/* 路由 + 评估器 全无 executor.sell/buy / auto_reeval.run_* / messages.create。

**v7.1.1 (2026-06-22) 录入免填金额 + 主页一键加测试仓** (用户: 粘 JSON 不想手填金额; 主页计算器旁直接加测试仓, 不用去 /paper 单独搞):
- `/api/paper/add` 金额逻辑改: 显式 `size_usd>0` → 直接用 (手动表单不变); 否则按主页**同一套 `position_size_usd` 公式**自动算 (q/入场价(=cur_price)/信心/止损档/距结算/cluster, 跟 `/api/suggested_size` 一模一样的调用), 公式=0(不建议)/拿不到 bankroll → `fallback_usd` (默认10)。返回带 `size_usd`+`size_reason`。
- `/paper` 粘 JSON (`addJson`) 改传 `auto_size:true`+`fallback_usd`+`days_to_resolution`, **不再传固定金额**; 原「每条金额$」框降级为「兜底$」(只在公式算不出时用)。
- **主页 JSON快速通道每条推荐加「🧪 加入测试仓」按钮** (`cjApplyPaper`, 排在 填入计算器 / 录入持仓 之间) → 一键 POST `/api/paper/add` 自动算金额。**不删该条** (测试归测试, 之后真买了还能点「📌 录入持仓」)。
- 🔒 仍只读不碰钱: 自动算金额只调 `position_size_usd`+`bankroll_usd`(读 cash 余额)+clusters(读持仓), 无 executor.sell/buy。实测 `/api/suggested_size` 同栈 live 返 $13.85 (bankroll $79.63)。

**v7.1.2 (2026-06-22) 测试仓显示抄主页主持仓 (一模一样)** (用户明确要求): `/paper` 列表 `load()` 重写成主页主持仓同款显示 ——
- `:root` 调成主页同一套配色 (paper 旧蓝调换成主页深底+绿 accent; `--card/--g/--r/--y` 起别名指向主页值, 旧 chrome 不破)。
- 加主页 `.pos-hdr/.pos-row` 同一 grid (`minmax(180px,2.5fr) 40 52 55 55 45 65 55 70 240`) + `.q-cell/.tp-input/.q-pct/.monitor-state-row/.ms-*` 徽章 (照搬主页 CSS, ms-* 用主页原色)。
- 列 = **名称/方向/距结算/入场价/当前价/份数/当前价值/盈亏%/盈亏$/q+信心+止损**, 行内 content 颜色照主页 (side 绿/红, 入场价紫, 现价青, 份数黄, 盈亏绿/红); 下面一行「**决策状态**: <ms-badge> · q=…|p=…|edge=…pp」跟真仓一致。
- q 输入改整数 % (跟主页 tp-input 一致, `saveQ` /100 后存 `/api/paper/update_q`)。`get_paper_positions` 是 `SELECT *` → q/confidence/stop_loss_tier/shares 全有。
- 保留 paper 独有: `would_sell` 预警行 (橙) + 📋重评/存q/🗑; 信心/止损档是只读小 tag (paper 无 saveConf/saveTier)。**仍不碰算法/不下单**。旧 `.prow/.side/stBadge/col` 变 dead code (无害)。

**v7.1.3 (2026-06-22) 两个修**: ① **q 显示 bug** —— v7.1.2 paper 行 q 输入只填了 `placeholder`(看着像要自己重填), 改成 `value=`(录入时 JSON 带进来的 q 直接显示, 跟主页 tp-input 一致; q 本来就存了, 纯显示问题)。② **测试仓 sizing 不吃 cluster cap** —— `/api/paper/add` 自动算金额时 `cluster_current_exposure_usd=0`(用户明确: cluster 集中度是真钱防过度集中的风控, 测试仓只为验证推荐准不准, 不该被同类真仓挤掉额度; 实测同一推荐 真仓 cluster 已占满→挤到 $0, 而 paper 给 $3.03)。**DD budget 仍照真仓**(用户只提 cluster, 没动月 DD 预算; 要不要 paper 也豁免 DD = 留给用户定)。

**版本**: 全线升 **v7.1** (2026-06-22): UI 版本号 + CLAUDE「v7.1 关键设计」+ 技术报告.md §二十八 + TECHNICAL_REPORT §28 + README×2 + SECURITY×2 (中英 parity; v7.0 保留历史)。代码注释 paper 标 v7.1。相关: [[plain-language-explanations]] (每次升级汇报)。

⚠️ 注: `git add -A` 上传时会顺带把用户并行的 /tags 功能文件 (tag_routes.py/scanner.py/data/*tag*.json) 一起提交 (已扫描无密钥无盈亏, 安全)。下次可更外科手术式只 add paper/docs 文件。
