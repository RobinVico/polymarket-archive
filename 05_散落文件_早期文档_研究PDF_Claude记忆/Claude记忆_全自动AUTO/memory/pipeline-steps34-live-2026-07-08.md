---
name: pipeline-steps34-live-2026-07-08
description: 2026-07-08 起第3/4步(auto_trader.py)已上线真钱自动交易; AUTO_FORCE_OFFLINE=1 永远离线=重评决策自动执行; E2E曾误买体育市场→加了宇宙白名单闸门
metadata: 
  node_type: memory
  type: project
  originSessionId: 2801e19a-0d58-4b6b-ab49-a10355b763ae
---

2026-07-08 当天(CLAUDE.md 可能滞后)项目实际状态:

- **第3+4步已上线**: `modules/auto_trader.py` (execute_for_slot), 由 auto_scheduler 在每轮扫描+选品后自动调用 → **真钱自动下单已激活**, 定时 09:00/21:00 全链路跑。手动触发 `POST /api/auto/execute_now`。
- **presence 已拍板**: `db.get_presence()` 里 `AUTO_FORCE_OFFLINE` 默认=1 → 本实例永远按"离线", 重评决策(含每天10:00全仓巡检)**自动执行动真钱**, 开着页面也不挂 pending。用户 2026-07-08 定"全部自动"。
- **护栏(Claude 默认值, env 可改)**: AUTO_TRADER_DAILY_CAP_USD=10 / AUTO_TRADER_MAX_POSITIONS=8 / 宇宙白名单闸门 `_in_universe` (tag 必须在 tags.py 白名单 + slug 必须出现在该 tag 扫描报告里)。
- **宇宙闸门的由来**: 2026-07-08 E2E 测试注入了体育市场(France World Cup)候选, 真买成交了 → 用户炸了 → 加此闸门, 该仓已 force_exit 清掉。
- **executor.buy 有 AUTO 分叉补丁**: 0.001-tick 市场步长凑整(step=10/gcd)、negRisk+tick 自动查(_order_opts)、makingAmount=USDC/takingAmount=股数(老项目标反已修)。
- **GLM 方向嗅探补丁**: `auto_reeval._confirm_new_q_direction` — new_q 疑似镜像翻转(实测 id=2: 持NO 应填0.90 填成 0.10)→ 自动反问 GLM 确认, 确认不了=本轮放弃。用户 2026-07-08 定的规则。
- **重评凭据实况**: 进程里只有 GLM key (provider=glm), 无 ANTHROPIC_API_KEY → 纯智谱。
- 用户开发协议不变: 一步一报、只列问题不擅自改、规则简单写死。2026-07-08 全代码审查后用户拍板修复, 三条 P0 规则由用户定:
  1. **GLM new_q 方向被反问更正后, 原 exit 不作数** → 再追问一次 final_action, 按最终答案执行; 拿不到=本轮放弃 (auto_reeval._confirm_new_q_direction)。
  2. **无档案仓一律不重评** (run_and_store 入口闸): 红色警示 (`no_meta_alert` 事件) 提醒用户手动补档案, 补完自然恢复; 用户接受这是对"巡检所有持仓"规则的修订。
  3. **临下单漂移容差 3pp** (`AUTO_TRADER_MAX_DRIFT_PP`): 下单前复核盘口, 漂移>3pp 或出 40~85 区间→放弃; 不做"ask≥q 就拒"的死卡 (用户嫌太严, 原话"别90变85这种就行")。
- 其他已修 (2026-07-08): 台账记实际成交额(解析"≈ $X.XX")、轮内去重+防对锁、trader/discovery 并发锁、候选 24h 过期(`AUTO_TRADER_CANDIDATE_TTL_H`)、paper 去重、追问语义扩到"JSON坏/字段废"且合法[]不再白追、宇宙闸门反引号精确匹配、record 键名(slug/original_confidence)+重试3次+cluster_id无'-'置空、启动时 key 隔离自检。
- 候选门槛边界用户二次确认: **≥5 就送** (恰好5个也送)。
- 2026-07-12: v8.0.x 独立版本线 (major 要用户批, minor 自主但告知, patch 自主); **文档同步铁律** = 改代码/版本必同步 version.py/横幅/监控页/CLAUDE/技术报告/README×2/memory/分享PPT (跑 /tmp/pptenv/bin/python3 scripts/gen_strategy_ppt_share.py)。8.0.1 = 监控页 v2 (曲线置顶/战报折叠只开当天/搬入只读重评建议+事件中心三榜+操作记录)。⚠️ 教训: 改 CLAUDE.md 用 Edit 精确锚定, 别用脚本 replace (曾因空串 replace 把文件炸成 25MB 并推送, 靠 amend+force 救回)。
