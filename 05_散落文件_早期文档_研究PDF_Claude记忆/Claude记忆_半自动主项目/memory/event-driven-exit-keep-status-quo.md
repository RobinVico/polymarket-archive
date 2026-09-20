---
name: event-driven-exit-keep-status-quo
description: "2026-06-18 评估给 event_driven 加止损/改重评退出逻辑, 用户决定保持现状不改; 真根因是重评 q 锚定现价"
metadata: 
  node_type: memory
  type: project
  originSessionId: c0f4c148-62b8-42d7-a3a7-e47259a6349f
---

2026-06-18 讨论: 用户反映重评常对深亏的 event_driven 仓位说 hold (例: 入场 $0.50 → 现价 $0.30, q=0.32, forward edge 仅 +2pp 仍 hold, 然后一路往下亏)。

**真根因 (比"缺止损"更深):** 盲评重评本应"看论点不看价" —— 无真新闻 → q 不动 → 价跌反而让 edge 变大 → 该 hold; 真翻盘新闻 → q 跌破现价 → exit。但实际 AI 把 **q 锚定到现价** (每跌一点就把 q 下调到比现价高 ~2pp), 于是 edge 永远显示"勉强为正", 既制造假 hold, 又毁掉本该理直气壮的 hold。用户的正确直觉: **退出该由"论点有没有被真新闻推翻"触发, 不由回撤 pp 触发** (买 60 飘到 50 但只有小新闻 → 该拿住)。

**评估过但全部未采纳的方案:** event_driven 加 -55% 兜底止损; 重评加 [反锚定硬规则 / 翻盘事件二元闸 / 入场预登记 kill-criteria / 催化剂时间窗 + 非事件软推翻]。

**2026-06-23 — 反向失败模式浮现 (死扛输家) + 研究提示词已备**: 反锚定(v7.0)修了"砍飞赢家"(错误A), 但带来反向问题: 重评偏向给高 q/扛, 用户反映"重评说别卖、后来亏很多"(错误B, 实例 Trump-MBS hold q=0.67→阴跌-38%卖、Tesla q 0.82→0.38 一路扛到-50%)。我用现有数据定性分析(样本仅~16重评决策/~9有结局, 不够定铁律): 扛错的规律 = ①"必须截止日前发生某事"但没发生→概率随时间衰减(该砍) ②收敛型/区间数据往不利走(该砍); 扛对的 = 押"维持现状/默认结果"侧(伊朗不结束浓缩→赢)。**关键张力: 防错误A(少砍)和防错误B(多砍)是一对矛盾, 任何改动必须同时压两头别复发**。已写深度研究提示词 `research_data/研究提示词_该砍还是该扛.md` (用户选: 学通用判别框架 + 数据全打包 + 同时防两头) + 数据包 `reeval_decisions.jsonl`(每次重评决策+之后真实曲线+结局, 脚本 `scripts/export_reeval_research.py`)。给外部深度研究 AI 跑, 出"该砍 vs 该扛"判别信号。尚未实施任何代码改动。

**2026-06-25 — 研究已跑完 (我自跑: 量化分类 + 联网核查4市场 + 独立quant回测两类错误)。核心结论 (写进 `research_data/研究结果_该砍还是该扛.md`):** 区分该砍/该扛最强信号 = **`must_happen` (赌"某事会在截止日前发生" vs 赌"不发生/维持现状")**, 远胜 tier/edge/亏损%。① 赌"不发生/现状"→时间站你这边→跌是噪音→**扛**(8/8 全对: 伊朗NO/俄军NO/Tesla NO/Cepeda); ② 赌"会发生"且没发生→时间衰减→**砍/卖一半**(唯一扛错=Trump-MBS"会通话"×2)。**edge 不区分对错**(Trump-MBS 扛错时 edge 还 +27pp, 反锚定抬高了 q = 假正edge, 印证用户抱怨)。**最扎心: 第一次崩坑底时"会赢的会发生型(JD Vance, 结算赢)"和"会输的(Trump-MBS)"本质不可分→诚实做法=会发生型第一次崩先卖一半(复用v7.0 partial), 再看q轨迹补刀。** **关键修复方向(不是删反锚定, 是划范围): 反锚定的"砸盘前中枢撑q"只对"不发生/现状"侧合理; "会发生"侧价格本就该随时间掉、不能拿中枢硬撑q(这正是Trump-MBS被抬到0.67扛错的根)。事件exit护栏不绕过而是喂它: 会发生型+窗口过60%+无进展+q下修→置thesis_broken。** 回测: 本规则完胜"一砍/碰止损砍"(抹$40-47砍飞、只多担$1.3), 比"一律死扛"$更高且去尾部亏, 比现系统(Trump死扛+JD Vance砍飞)两头都改善。**⚠️样本极小: 真扛错就1个市场(Trump-MBS)、砍飞就1个(JD Vance), 只够方向不够定阈值; must_happen 要重评AI自己标。待用户拍板才改代码(5步: must_happen标记/反锚定划范围/时间衰减喂护栏/会发生型卖半/记校准数据)。**

**决定 (2026-06-18): 用户选「不要改, 保留现有」** —— event_driven 维持不设 %止损 (只 $0.05 地板), 重评提示词原样, -55% 不加。备注: `prompts.py:299` 已有"持续非事件=反向事件"、`:206-213/:294` 已有反锚定纪律 (只是实践中不够强); 决策口径见同 repo 的 monitor.py STOP_LOSS_PCT_BY_TIER。

**2026-06-21 更新 — 用户重新提起, 现有实打实 $ 证据 (复盘 6/8 后 16 笔):** 净实现 −$0.12 (止盈 +$12.18 被砍仓 −$12.30 完美抵消 = "绕一圈回原点")。重评建议卖 7 笔 −$7.79 是最大失血点, 全在 event_driven/政治外交。**两个已结算确认卖飞的赢家: #79 伊朗关领空 (−54% 割, 结算赢, 少赚 $9.29)、#86 JD Vance 会伊朗 (−43% 割, 结算赢, 少赚 $6.68) = 合计 ~$16 (账户 ~20%)**。历史全样本: 38 个亏损卖出里 16 个 (42%) 最终会赢。根因仍是重评 q 锚定现价 (suggestion #11 实锤: new_q 0.31 vs 现价 0.395, AI 原话"低于市价")。**完整复盘文档: `分析报告_6月8日后平仓复盘.md` (gitignore 本地, 含真实 P&L, 可由 v4.db 重生成)。** 我给的修复建议 (待用户拍板, 可叠加): ①重评 prompt 禁止 q 锚定现价 ②event_driven 的 exit 仅 thesis_broken=true 才允许 (代码加闸) ③退出要更大负 edge (事件型 <−15~20pp) ④入场必填 tag (16 笔有 8 笔无 tag)。**"别主动再提"已失效 (用户主动重开此题); 下次大概率要动手修, 等用户选方案。**

**2026-06-22 已实现并上线 = 大版本 v7.0 (用户把第一位数字从 6 升到 7; 选"根因+出场机制", 不含自动加仓):**
- **根因①**: 重评新增"大跌前价格中枢" `auto_reeval._pre_dump_center` (get_prices_history 取 trailing 窗口排除最近 6h 的中位数), 喂进 prompt (`build_reeval_prompt(pre_dump_center=)` + 指令尾) 让 AI 别锚坑底现价。`run_and_store` 算一次挂 `pos['_pre_dump_center']` + 落库 (db `auto_reeval_suggestions.pre_dump_center`/`price_curve` 两新列)。
- **根因②**: `auto_reeval.guard_event_driven_exit(action,decision,tier,cur)` —— event_driven 的 exit 必须 thesis_broken 或 edge≤ -8pp 才放行, 否则降级 update_q。**两处调用**: 离线 `_auto_execute` + 在线 `dashboard.auto_reeval_confirm` (卖之前、claim 之后)。**默认安全**: new_q 缺失就持有。
- **出场③ 止盈分档** (monitor `_evaluate_position` 1a): event_driven ≥0.92 卖一半(`partial`+`tp_half_sold`, **check_once partial 分支绝不 clear_meta**, 让另一半跑——且 0.90 通用全卖规则已排除 event_driven); convergent ≤3天 0.88 全卖; 其余 0.90 全卖。
- **出场④ 收敛型移动止损** (仅 convergent): 从 `position_meta.peak_price` (每心跳 max 更新) 回撤 ≥20%(≤3天 12%) + 连 `TRAILING_CONFIRM_ROUNDS`=6 拍确认 (内存 `self._trail_breach`, 重启清零=只延迟不误触发) → 走现有 PENDING_REEVAL/硬卖。hybrid/legacy 维持入场锚。**关键**: `_maybe_trigger_auto_reeval` 加 `state=='PENDING_REEVAL' 跳过 entry 锚 gate`, 否则收敛型在盈利时的移动止损会卡死(既不卖也不触发重评)。
- env 可调: `AUTO_REEVAL_CENTER_WINDOW_H`(24)/`CENTER_SKIP_H`(6)/`EXIT_GUARD_EDGE`(0.08); monitor 常量 TRAILING_STOP_PCT_CONVERGENT(0.20)/_NEAR(0.12)/TRAILING_CONFIRM_ROUNDS(6)/TP event_driven 0.92 半/convergent_near 0.88。
- 已测: 5 文件 ast/import OK; guard 6 用例; partial(卖半不清meta+不重复+余量跑); 收敛移动止损连6拍确认+恢复清零; center 合成砸盘曲线→0.50(非坑底); 重启干净 HTTP200, peak_price 实写 (两持仓均 convergent)。⚠️ 阈值是 51 笔小样本低置信度, 先观察再校准。✅ docs 全部升 v7.0: 技术报告中英 §二十七/§27 + CLAUDE「v7.0 新增的关键设计」+ README×2(当前版本概要/安全) + SECURITY×2 + 所有 UI 版本号(主页/历史/面板/手机/footer) + 代码注释 v6.1→v7.0。**复检发现并修的 3 个问题** (详见下): ①event_driven 卖半后剩余被 0.90 通用全卖→已排除 event_driven ②收敛移动止损盈利时卡死→_maybe_trigger 对 PENDING_REEVAL 跳 gate ③price_curve 大字段进轮询响应→两路由 pop 掉。Kostyantynivka "数据对不上"=假警报 (我们持 No@0.787, 报告比错成 Yes 侧)。
