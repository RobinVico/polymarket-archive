# Polymarket AUTO (全自动账户版) 项目规则

> 2026-07-06 从 `~/polymarket` (半自动老账户, 当时 v7.4.3) fork 出的**独立副本**; 已同步老项目 v7.4.4 (混合型移动止损) + **v7.4.5 (2026-07-08 晚: 混合型砸穿止损线【直接平仓】不走 API 重评, 收敛/事件仍先交重评; monitor.py 整文件同步 + dashboard tooltip/autobot 横幅/version.py 手术式移植, tags 铁律拆除处已验证 0 残留)**。
> 目标: **全自动交易, 零人工** —— 定时扫描 → GLM 选品 → 写死规则分流 → 自动买入 → 盯盘 → 定时+大跌自动重评 → 自动出场。LLM 全部用智谱 GLM (两把 key 分工)。
> **当前状态**: 第 1 / 2 / 2.5 / 3 / 4 步**全部上线** (扫描→选品→分流→真买/测试仓→巡检重评一条龙, 定时 09:00/21:00 自动跑); 账户已打通 (sig=3, 现金 ~$50.76), 真钱闭环测试完成; 2026-07-08 全代码审查 16 项修复已落地 (见「审查修复」)。

## 开发协议 (用户 2026-07-08 定, 最高优先级)

- **一步一报**: 每个步骤 = 先用大白话讲这步做什么/花不花钱/动不动钱 → 用户点头 → 实现+实测 → 汇报 → 提出下一步再等点头。**绝不一次全加**。
- **规则要简单写死**: 用户明确否掉 edge 门槛/GLM双跑一致/信心分流/流动性检查那套复杂闸门 —— **别自作聪明加回来**; 想加任何保护先问。
- **新代码只放独立新文件** (`modules/auto_*.py`, 路由从 autobot.py 注册): 绝不改同步自老项目的模块 (monitor/dashboard/auto_reeval/db/…) → 以后从老项目同步策略更新永远零冲突。
- 对用户汇报用大白话三段式, 拿真实仓位举例, 别甩术语。

## 版本号规则 (2026-07-12 起 AUTO 独立版本线; 单一来源 = `modules/version.py:VERSION`)

> 沿用老项目 2026-07-05 的规则, 只是 AUTO 从 **8.0.0** 起走自己的版本号, 跟老项目 7.x **彻底分家、不再同步** (此前"version.py 跟老项目同步走"作废)。老项目那边加东西**不自动进本项目**。

- **格式 `major.minor.patch`**。启动日志 (autobot 横幅动态读 `VERSION`) + 首页 + GitHub 发布版本全部读 `modules/version.py`, 改一处全同步, 别处别写死。
- **major (整数)**: ⚠️ 只有用户明确说才改, **需用户审批**。
- **minor (小数1位)**: 重大更新 (新增较大功能), Claude 可自行改**但必须告知用户**; 一次上 N 个大功能就 +N。改动**详细记入技术报告变更日志**。
- **patch (小数2位)**: 小改动 Claude 自行决定、不用审批; 技术报告记关键词简介即可。
- **📌 文档同步铁律**: 改任何策略/代码/版本后, 下面全部**当次同步、一个都不能漏**:
  1. `modules/version.py` VERSION (单一源)。
  2. `autobot.py` 启动横幅那行**策略描述** (别让它撒谎; 版本号它已动态读 `VERSION`, 不用手改)。
  3. `modules/auto_dashboard.py` 首页 (若展示版本/规则处)。
  4. `CLAUDE.md` 变更日志 + 相关设计段。
  5. `技术报告.md` 变更日志 + 相关章节。
  6. `README.md` **和** `README.zh.md` (版本号)。
  7. 相关 memory。
  8. **分享版 PPT** `scripts/gen_strategy_ppt_share.py` → 重新生成 `Polymarket_AUTO_项目分享_v{VERSION}.pptx` (改版本/策略后: 更新版本号 + 封面/运行页真实数据; 跑 `/tmp/pptenv/bin/python3 scripts/gen_strategy_ppt_share.py`, `/tmp/pptenv` 若丢了 `pip install python-pptx` 重建)。
  - AUTO 有上面第 8 项那份**分享版 PPT** (给熟人看, 2026-07-12 从老项目分享版 fork 改写); **没有**老项目的 SECURITY 文档 / 内部版 PPT (`gen_strategy_ppt.py`, 没搬) / 英文 TECHNICAL_REPORT, 那几项不适用。
  - **改完必验证** (沿用老规则): `grep` 一遍确认旧版本号无残留 —— 只有真该改的地方改了; ⚠️ 继承自老 monitor/策略的 `7.4.x` **同步语境**(如"止损三档同步老项目 7.4.5")是正确的、**保持不动**, 别误当残留改掉。
- **变更日志**:
  - `8.5.5` (2026-09-01, patch, **用户令: 停掉花钱的 API 部分, 仓位和其余程序继续**) = ① **根因**: 智谱在 08-12~08-27 停机期间改了 Web Search API —— **无视 `count` 参数, 恒返 50 条** (实测 count=15 / count=50 都回 50 条 ~95k 字符)。8 轮搜索把 context 从 ~15万 顶到 **30~50万 tokens**, GLM 消化不完 → 撞 8.3.2 的 20min 硬熔断。近 7 天 13 次超时 (World 4 次最惨), 且 **prompt tokens/轮 1.4M→3.0M 翻倍烧钱**。另有 2 次智谱内容过滤挡 China (老毛病, 同规则16)。**代码没动过, 是上游变了。** ② **执行关停**: (a) `.env` 的 `ZHIPUAI_API_KEY_DISCOVERY` 改名 `..._OFF` 停用 → 选品照常**免费扫描**但不调 GLM (走 `is_configured()=False` 的既有分支); (b) `set_api_paused(True)` 关掉全部重评 (GLM + Claude 兜底一起关, 因为 `is_enabled()` 在选模型之前)。 ③ **顺带修 bug**: 官方那个「API 紧急暂停」开关**原本挡不住每天 15:00 的全仓巡检** (`run_and_store` 入口没查 api_paused) → 在 `auto_daily_reeval.maybe_run()` 补 `get_api_paused()` 早退, 让开关名副其实。 ④ **继续跑的**: monitor 止盈/止损 (纯价格逻辑, 零 API)、bench 亏30%止损、shadow 入场−60%止损、三个监控页。**不会有新买入** (没候选了)。恢复 = `.env` 去掉 `_OFF` + 主页「API模式」按钮取消暂停。
  - `8.5.4` (2026-08-27, patch, 用户要求) = **资产曲线剔除停机空档 + 三账户综合报告生成器**。① `auto_dashboard._adjusted_portfolio_history` 两处加固 (只动服务端, **前端 loadChart 共用部件一个字没改**, 守 8.5.1 用户令): (a) 剔除**开机瞬间假点** —— 那一拍只读到现金、持仓还没拉回来, 会在曲线上戳假崩盘坑 (08-27 重启时 bench 被戳了个 $28.85 的坑); (b) 相邻点间隔 > `AUTO_CURVE_GAP_BREAK_SEC` (默认 6h) = bot 关着无人打点 → 插 `y=null` 断点, Chart.js (spanGaps 默认 false) 自动断线, **不再拉直线跨过停机期**; note 报"已断开 N 段停机空档"。② 新只读脚本 `scripts/gen_3acct_report.py` → `三账户报告-<日期>.pdf` (3 页, 复用 gen_run_report 的 CSS/helpers): 三账户 KPI + 收益率曲线 (SVG, 空档已折叠) + 准确率按价位桶 + 三策略横向对比 + 主账户明细 + 账实不符专章。**口径铁律: 以资产真相为准 (现总资产 − 净投入), 逐笔台账只作明细** —— 归零卖不掉的废仓和 bench 的 vanished 仓永不进台账, 只看台账会高估战绩。
  - `8.5.3` (2026-07-24, patch, 用户要求) = **`/shadow` 三号账户独立监控页** (`modules/auto_shadow_dashboard.py` 新文件, 照 8.5.1 钦定模式 = 主页克隆换数据源, 共用部件逐行照搬 bench 克隆模板): 导航(含恐龙)/四磁贴/资产曲线(成本线+区间涨跌)/当前持仓面板(chips=q·信心·止损线) + shadow 专属区 (已结算战绩/落袋盈亏/-60%止损数/总条目 磁贴 + 候选处理审计 + 事件流 + 全部条目表 + ▶立即扫描按钮)。接口 `/api/shadow/holdings|history|monitor` 形状对齐主页; `auto_shadow.py` 加 `shadow_snapshot` 表 + 每10min打点 (曲线数据源)。**主页 + /bench 导航加「🟣 三号低价」按钮**。
  - `8.5.2` (2026-07-24, patch, 用户提供凭据) = **三号账户 shadow 转真钱** + 两处加固: ① 用户提供第三账户凭据 (funder 0x812D…1Ce0, sig=3 只读验证通; 余额 $0 待充值) → `.env` SHADOW_POLY_* + `SHADOW_DRY_RUN=0`; dry→real 切换 start_at 自动重置 (只买此后新推荐)。② **宇宙闸门复查**: shadow 真买前用 `auto_trader._in_universe` 自己再验一遍 (tag白名单+slug在扫描报告+黑名单拒), 不信任 status='paper' 的来源 (发现 auto_candidates 里有 id 9000019+ 的合成测试行, 07-08 体育误买铁律适用于任何真钱账户)。③ **现金不足→暂缓不作废**: 候选不标 done, 24h 保鲜期内每轮重试, 充值到账自动补上车 (原逻辑会把到账前的推荐永久跳过); 告警 10min 节流。④ **心跳** shadow_state.last_tick 每拍写 (状态API暴露, "没动静"≠"死了")。dry E2E 已验: 3 个真实候选全部按规则点名跳过 (两个≥0.85贵半、一个推荐0.37临下单漂到0.41出线)。
  - `8.5.1` (2026-07-24, patch, 用户返工令) = **/bench 页重做 = 主页克隆换数据源** (用户: "别乱改, 共用部件保持原有的")。导航(含恐龙)/四磁贴(总盈亏/持仓数/现金/总资产)/资产总值曲线(区间按钮+成本线+区间涨跌头, `loadChart` 逐行照搬)/当前持仓面板(pos-panel 十列布局照搬, 去"操作"列, chips=q·信心·tag) 全部照抄 auto_dashboard.MONITOR_HTML; 接口 `/api/bench/holdings`/`/api/bench/history` **形状刻意对齐主页同名接口**让照搬 JS 零改动。bench 专属区(第二排磁贴: AI准确率/落袋/止损数/总条目 + 准确率桶/双台账/事件流)同款卡片放下方。服务端补: bench_positions 加 `end_date` 列(距结算), bench_snapshot 加 `pos_cost` 列(成本线)。**主页导航加「🧪 Bench基准」按钮** (auto_dashboard.py pages-tab 一行, AUTO 自有文件)。
  - `8.5.0` (2026-07-24, minor/新功能, 用户拍板) = **三号账户 shadow「低价拿到底」** `modules/auto_shadow.py` (独立新文件): 把主策略送测试仓那半的推荐在第三个账户【真买】。规则死: 只吃 `status='paper'` 候选 ('paper:黑名单强制' 天然不吃=黑名单永不真买; 宇宙闸继承), 临下单新鲜 ask **≤0.40** 才买 (≥0.85 那半永远排除), **$2/仓** 固定, **止损不止盈** = 入场锚 **−60%** + $0.05 地板 (连3拍确认), 无止盈/无重评/无时间止损 — 拿到结算; **只买启用后的新推荐** (存量不补, start_at 落库, dry→真钱切换时重置)。止损值依据 07-24 回撤研究 (18条低价仓真实路径: 唯一真赢家胡塞0.38→$1 中途最深跌−55%、输家全奔零 → −60%放得过赢家; −50%会杀赢家, 数据反对)。隔离照抄 bench 全套 (env换SHADOW_POLY_*构造第二实例·自带_positions/_cash·同凭据守卫拒启·主线程 app.run 前构造); 自建表 shadow_positions/shadow_done/shadow_state; pending先落库=崩溃不重复买; 路由 /api/shadow/status + scan_now。(07-24 当天已转真钱, 见 8.5.2。)
  - `8.4.1` (2026-07-24, patch, 用户拍板) = **Bench 转真钱 (老半自动账户接入) + 独立监控页**。① 老 bot (5051, 空转11天/0持仓) 用户拍板杀掉, 老账户凭据 (sig=1, $90.47) 进 `.env` BENCH_POLY_* → `BENCH_DRY_RUN=0` 真钱模式, 实测第二账户实例构造/余额查询全通; dry 模拟数据清空 (真实 score_only 记分行保留); 游标在最新候选 → 首批真实 $2 买入 = 下一个扫描点。② **`/bench` 独立监控页** (`modules/auto_bench_dashboard.py` 新文件, 设计系统与全自动主页同源): 指标磁贴 (总资产/AI准确率/落袋/浮动) + 资产曲线 (新表 `bench_snapshot`, bench 线程每10min打点) + 准确率by价位桶 + 持有中实时仓 + 双台账全条目 + bench 事件流 + 手动触发按钮; 30s 自刷新。auto_bench.py 的简版页面让位 (只留 /api/bench/*)。
  - `8.4.0` (2026-07-23, minor/新功能, 用户拍板) = **Bench 第二账户基准策略** `modules/auto_bench.py` (独立新文件) + `/bench` 页: 同一份选品推荐照单全收 (黑名单完全忽略/反方向不对锁只记分), $2/仓固定, 唯一卖出=亏30%瞬时清仓, 无重评无止盈, 持有到结算, **双台账** (钱的账含止损; AI预测的账止损后照样等结算判对错 → 止损不污染准确率)。目的: 拿掉"提前卖出"变量测 GLM 裸预测准确率 (75% vs 47% 缺口的对照组)。第二账户隔离: env 临时换 BENCH_POLY_* 主线程直接构造第二 Executor 实例 (绝不碰 .get() 单例/绝不用 get_positions 的 FUNDER 全局/绝不写 _live_cash 类属性), 同凭据守卫拒启, 主 monitor/重评看不见 bench 仓。bench_positions 表 UNIQUE(cand_id)+pending先落库=崩溃绝不重复买。**现 BENCH_DRY_RUN=1 纸上模拟**, 等用户给第二账户凭据 (BENCH_POLY_PRIVATE_KEY/FUNDER, sig=3) 转真钱。离线18项测试+dry E2E 全过。
  - `8.3.3` (2026-07-21, patch/策略, 用户拍板) = **8.2.0 校准收口: prompt 五折从"覆盖"改成"物理删除"** (见规则17 + 分叉#8)。DISCOVERY/REEVAL prompt 里"打五折"校准整段删净 (`市场价+0.5×…` + 所有"校准后 edge/估算" + REEVAL 的 A6/B3 校准步), GLM/手动贴Claude **都只给原始估算** ("原始输出什么就是什么", 用户 2026-07-20 令)。去掉 8.2.0 加的 `JSON_APPEND`/`GLM_JSON_INSTRUCTION` "别校准"覆盖 (prompt 已无 0.5, 覆盖多余)。Python 0.8 校准 (`auto_calibrate`) 不变、仍只自动链路调 → **手动流程现在是纯原始 q 无校准**。prompts.py 成 AUTO 分叉。实测: `calibrate_q(0.80,0.50)=0.74` 照旧; prompts.py `grep 校准|q_calibrated|市场价+0.5` = 0。
  - `8.3.0` (2026-07-18, minor/策略, 用户拍板) = **止损/重评再改三项** (分叉补丁7): ① 收敛型砸穿 = **直接平仓不重评** (`_direct_stop` 加 convergent; 原"交重评"作废, PENDING_REEVAL 退役), 盘中不再做亏损触发重评。② 事件型盘中重评触发改「**任何盈亏水平、从持有期最好点回撤 ≥5pp 触发1次**」(去掉 -30%门槛 + 6h冷却; 基线取最好点、触发后重置=单次暴跌只算1次; `AUTO_REEVAL_RETRIGGER_DROP` 0.10→0.05)。③ **删 `cancel_autostop`** (重评不能再关止损; prompt/schema 移除 + `_auto_execute` 中和为 hold; 手动"止损OFF"暂留)。混合型不变; 每天15:00全仓巡检重评照旧。改 monitor.py + auto_reeval.py + autobot 横幅。
  - `8.2.0` (2026-07-18, minor/策略, 用户拍板) = **q 校准从 prompt 内"打五折"改成 Python 端"打八折"** (见规则17): prompt (DISCOVERY/REEVAL) 不再让 GLM 自算 `市场价+0.5×(q_raw−市场价)`; 自动链路机器指令 (`JSON_APPEND`/`GLM_JSON_INSTRUCTION`) 覆盖成"GLM 只给**原始真实 q_raw**", 校准挪到 Python 统一做一次 = `市场价 + AUTO_Q_TRUST(0.8)×(q_raw−市场价)`, 选品(`auto_discovery._normalize`)+重评(`auto_reeval._run_one`, 方向纠错闸后) 都打。信自己 80% (旧 0.5→0.8, edge 更大/更敢下)。单一来源 `modules/auto_calibrate.py`; 旋钮 `AUTO_Q_TRUST` (1.0=原始/0.5=复现旧五折/0.0=纯市场)。⚠️ **prompts.py 没删五折** (它跟 dashboard.py 还活着的手动贴Claude流程 `/api/reeval_prompt` 共用、那条没 Python 步), 靠覆盖防双重打折。实测: `calibrate_q(0.80,0.50)=0.74`。
  - `8.1.0` (2026-07-18, minor/策略, **用户最高指令**) = **事件型出场两改** (分叉补丁6): ① 加 **-50% 强行止损** (`EVENT_DRIVEN_HARD_STOP_PCT`) — 跌破成本 -50% 直接平仓, 早于重评/护栏/手动关止损、任何东西越不过 (依据: 仓位回撤分析 -50% 是"不归点"; 原 -60%→交重评作废)。② **删事件型 exit 护栏** `guard_event_driven_exit` (原需 thesis_broken 或 edge≤-8pp 才放行, 否则降级 update_q) — auto_reeval+dashboard 两处删净, GLM 判 exit 立刻执行。方向纠错闸 `_confirm_new_q_direction` 保留 (仍防数字填反)。改 monitor/auto_reeval/dashboard + autobot 横幅 + PPT-P7。
  - `8.3.3` (2026-07-23, patch) = **单仓硬顶 $15→$5** (用户: 7-21 地震仓公式给 $11 占本金 ~11%, 嫌单仓太大)。env `SIZING_MAX_SINGLE_POS=5` 覆盖, sizing.py 不动; Kelly/信心/cluster 逻辑不变, 只是最后那道硬顶从 15 收到 5。实测: 原 $10.79 仓现被夹到 $5, 本来 <$5 的小仓不受影响。
  - `8.3.2` (2026-07-20, patch) = **选品单 tag 硬超时熔断** (用户: 7-20 晚 Iran 汇总调用挂死 2h 冻结整轮+攥着锁害得次日 09:00 会被跳过)。`AUTO_DISCOVERY_TAG_TIMEOUT_S` (默认 1200s/20min): 单 tag GLM 超时→踢掉该 tag(卡死子线程 shutdown(wait=False) 丢后台)、补记 discovery_runs 报错行、其余 tag 照常并发跑完。=0 关熔断。**已确认: 有推荐立刻下单(独立消费线程 run_execution_consumer 每3s执行)本就不等其他 tag, 无需改。**
  - `8.3.1` (2026-07-20, patch) = 往期仓位监测页仓位卡片**默认折叠** (用户): 只显示 标题(去尾部数字代码) + 汇总盈亏%/$, 「详情」按钮展开回原 sell-card 明细。新文件 `modules/auto_history.py` import dashboard 的 HISTORY_HTML + 运行时注入 style/重定义 renderClosedRowList, autobot 覆盖 /history view_functions; **dashboard.py 一字未改**, 分析/图表/导出/展开明细全原样继承。
  - `8.0.6` (2026-07-18, patch/策略) = **删除月度回撤预算闸** (用户拍板: 18仓 $29.5/$30 打满 → 今早5条推荐全拒; 今早算缺勤不补, 21:00 起正常)。env SIZING_MONTHLY_DD_BUDGET=999999 功能性删除, sizing.py/cluster 20% 上限不动。实测: 今早被拒输入现在给 $4.58。
  - `8.0.5` (2026-07-16, patch) = 资产曲线出入金校正 (用户: 入金$50把曲线搞断): 新只读接口 `/api/auto/portfolio_history` — 识别「相邻快照 Δcash≥$5 且 Δassets≈Δcash」= 出入金 (买卖/结算是现金↔持仓对倒不误判), 入金前历史整体抬到当前本金口径 → 曲线连续/终点=真实总资产/区间涨跌=纯交易盈亏; 预热点裁剪挪到服务端; 图表标注"已校正出入金"。阈值 `AUTO_DEPOSIT_JUMP_MIN` (默认$5)。老 /api/portfolio_history 不动。
  - `8.0.4` (2026-07-12, patch) = 事件中心整块换成老页原版 JS/HTML (Top3/More·pp$切换·↻强刷·5分钟自刷新·原行样式); 导航栏加回老页的 Chrome 小恐龙动画 (🦖🦕躲🌵)。
  - `8.0.3` (2026-07-12, patch) = 监控页三调 (用户): 删独立警报中心 (警报已在按天战报内) / 事件中心移到重评建议前 / 重评建议改回老版折叠卡样式 (单行+更多▾展开, 只读无按钮)。
  - `8.0.2` (2026-07-12, patch) = 战报折叠改版 (用户二次明确): 主区只显示当天一张卡, 其余所有天收进**一个**「📁 往期战报」折叠盒 (盒内每天再各自折叠)。
  - `8.0.1` (2026-07-12, patch) = 监控主页 v2 布局 (用户指挥): 资产曲线移到最上、按天战报只展开当天其余折叠、老页三区搬入 —— 自动重评建议 (完整只读: 触发/决定/q变化/新闻/理由/状态)、事件中心 (实时榜/涨跌榜/现值榜)、操作记录 (全事件流); 监控页显示版本号。
  - `8.0.0` (2026-07-12, **major**, 用户拍板 = AUTO 独立版本线起点) = 把已上线的整套全自动流水线收成 8.0: 流式"扫一个喂一个" 4 路并发选品 (每 tag 即时重扫拿新盘口) + 有推荐就立马下单 (生产者-消费者, 下单串行) + 反向推荐触发持仓重评 + GLM 多轮自主搜索 (`auto_glm_agent`) + 全自动监控新首页 `auto_dashboard`。此前 AUTO 进度不占版本号 (见 git log `0c277d2` 起)。

## 与老项目的隔离铁律 (用户 2026-07-06 定)

- 本目录 `~/polymarket-auto` 与 `~/polymarket` (老账户, 端口 5051) / `~/polymarket-semi-auto` (v3, frozen) **零关联**: 各自 .env / 数据库 / venv / git 仓库, **绝不读写那两个目录** (从老项目"同步策略代码"= 单向复制文件过来, 是唯一例外)。
- 本仓库唯一 remote = `origin` → GitHub `RobinVico/polymarket-auto` (**private**)。老项目的 dev/public 双仓、cron auto-backup、脱敏发布**全部不适用**。
- 端口 **5052** (老 bot 占 5051)。
- **结构性防误杀 (2026-07-07)**: 入口文件叫 **`autobot.py`** (故意不叫 main.py!) —— 老项目文档里的 `pkill -f "main.py"` 永远匹配不到本进程, 反之亦然。**永远不要改回 main.py**。杀本进程只用: `bash restart.sh` 或 `lsof -ti tcp:5052 -sTCP:LISTEN | xargs kill -9`。
- 老账户的密钥/数据一概不进本目录; 新账户凭据只写本目录 `.env` (gitignored)。**用户拍板的唯一例外 (2026-07-24)**: 老半自动账户 (funder …E07E, sig=1, 当时余额 $90.47) 被启用为 **Bench 第二账户** — 其凭据已拷入本目录 `.env` 的 `BENCH_POLY_*` 键 (从老项目 .env 只读了这三行, 老项目目录其余照旧绝不读写)。老 bot (5051 main.py, 空转11天/0持仓) 已由用户拍板杀掉; **老 bot 永远不要再启动** — 它的 monitor 会按老策略卖 bench 的仓, 基准测试就废了 (cron 只有备份脚本, 不会自己重启它)。

## 用户已拍板的流水线规则 (2026-07-08, 都是死规则)

0. **宇宙铁律 (用户原话: "所有的都按原本老的执行, 只代替我手工的部分")**: 系统**只能**交易「白名单 tags (modules/tags.py) 扫描报告里真实出现的市场」。auto_trader `_in_universe` 双重闸门: tag∈白名单 + slug 必须在该 tag 的扫描报告文件里, 真买/测试仓一律适用。⚠️ 事故记录: 2026-07-08 Claude 做 E2E 测试手动注入了体育市场 (法国世界杯) 买成真仓 → 用户炸了, 立即清仓 (磨损几分钱) 并加此闸门。**永远不要为了测试注入宇宙外市场; 测试真买通道用白名单 tag 报告里的真实市场。**

1. **定时扫描**: 每天 **09:00 / 21:00** 本机时间全扫 (tier 1+2, **中范围 medium**)。用户 2026-07-08 拍板: 全自动链路**只用中范围** (标准扫描太严, 首晚 9 个 tag 全 <5 候选零调用; 大范围不用)。手动页面扫描模式照旧三档可选, 自动链路写死 medium **别改回**。
2. **GLM 选品**: 扫描完自动跑; 回复**"给的不对" (没 JSON / JSON 坏 / 字段全非法) → 再发一条消息追问 (只追问一次)**, 再失败 = 本 tag 本轮放弃, 记日志。**合法空数组 `[]` = 正经"无推荐", 不追问** (2026-07-08 审查修正: 老代码会白追一次)。
3. **分流写死**: 推荐**现价 0.40 < p < 0.85 → 真买** (按计算器 `position_size_usd` 金额); **否则 (含恰好等于 0.40/0.85) → 自动进测试仓**。没有其他任何闸门。
4. **测试仓零操作**: 进去之后**不重评、不提醒、无任何后续操作** (省 API); 免费盯价+模拟卖点记录保留 (走公开行情, 零成本)。
5. **两把智谱 key 分工, 绝不混用**: `ZHIPUAI_API_KEY_DISCOVERY` = 选品搜索; `ZHIPUAI_API_KEY_REEVAL` = 重评 (autobot.py 启动时映射给老代码读的 `ZHIPUAI_API_KEY`)。智谱后台按 key 分开记账。
6. **24h 全仓巡检重评**: 每天 `AUTO_DAILY_REEVAL_HOUR` (默认 **15**, 用户 2026-07-09 从 10 点改到下午 3 点) 点, **4 路并发工作队列** (`AUTO_DAILY_REEVAL_CONCURRENCY`, 用户 2026-07-10: 串行太慢学选品, 一个评完下一个顶上; 配套 `AUTO_REEVAL_STALE_ANALYZING_MIN=90` 放宽判死线 — agent 深搜单仓 30~60 分钟, 老的 30 分钟线会误杀, db.expire_stale_auto_reeval 有 AUTO 补丁读它), **所有【有档案】持仓** (含盈利仓/止损OFF仓) 逐个重评, 走重评 key; 跟大跌触发那条路独立、经 inflight 锁互斥。**无档案仓一律不重评** (2026-07-08 用户拍板): 方向/q/tier 无从谈起, 老行为会默认成 YES 反着评; 挡在 `run_and_store` 入口 (巡检+大跌两条路全管), 🔴 `no_meta_alert` 事件流红色警示, 用户手动补档案后自动恢复。
7. **不加**请求频率上限 (用户否掉); **IP 分离先不动** (讲解过方案: 首选给本 bot 配 HTTPS_PROXY 每进程代理, 等纸上阶段看真实调用量再定)。
8. **tags 永远不变 (2026-07-08 用户铁律)**: 动态热门标签功能 (按交易量每日建议/采纳 tags) **在本仓库整体删除** —— `modules/tag_discovery.py` + `modules/tag_routes.py` 文件已删, scanner 的动态合并/动态解析已拆 (只认 tags.py), dashboard 的 /tags 页+路由+导航链已拆。宇宙 = tags.py 白名单, 改 tags 只能用户改 tags.py。⚠️ 同步老项目代码时: **永不把 tag_discovery/tag_routes 拷回来**; 拷 scanner.py/dashboard.py 时必须重新拆这几处 (grep `tag_discovery|tag_routes|/tags` 验证为 0)。
9. **单 tag 候选门槛 (2026-07-08, 用户确认按"单个标签"算; 边界二次确认: ≥5 就送, 恰好 5 个也送)**: 一个 tag 扫出的候选市场 **< 5 个 → 该 tag 不送 GLM** (`AUTO_DISCOVERY_MIN_CANDIDATES`, 默认 5), 省 API。跳过名单必须记日志不许静默。⚠️ 当前 scanner 筛得严, 多数日子可能全部 tag 都 <5 = 零调用 — 这是用户明知后果选的; 嫌太严改 env 一行。手动 `discover_now` 指定单 tag 时**不受门槛限制** (显式测试行为)。
10. **临下单漂移容差 (2026-07-08 用户拍板, 值由 Claude 定)**: 真买下单前最后复核一次盘口, 相对算金额那次的价**漂移 > 3pp** (`AUTO_TRADER_MAX_DRIFT_PP`) 或**漂出 40~85 区间** → 这单不追, 点名跳过。用户原话口径: 流程是秒级的, 正常动不了多少, "别 90 变 85 这种"; **不做 "ask≥q 就拒" 的死卡** (用户嫌太严)。
11. **重评方向纠错两道闸 (2026-07-08 用户拍板)**: ① new_q 疑似镜像翻转 → 反问 GLM 本人要 `new_q_held_side`, 确认不了=本轮放弃; ② **数字被更正过且原决定是 exit → 再追问一次 `final_action`** (原 exit 是基于反方向 q 给的不作数), 按最终答案执行, 拿不到=本轮放弃不动仓。
12. **反向推荐触发重评 (2026-07-10 用户拍板)**: 选品推荐了「已持仓位的反方向」→ 防对锁照旧拒买, **同时立刻触发该持仓一次正规重评**, 并把反向推荐的理由原文注入重评 prompt (`pos["_trigger_note"]` → `auto_reeval._build_prompt` 喂给模型, "既不盲从也不护短")。守卫: inflight 互斥 + **6h 同类触发去重**; 决策走现有管道 (方向纠错闸+离线自动执行)。dashboard 重评卡的触发原因显示"反向推荐触发: …"。
13. **关键词黑名单 → 只进测试仓, 不再硬排除 (2026-07-12 用户改口径; 原 2026-07-10 是"永远排除")**: 黑名单关键词命中**标题/slug** 的市场**不再从扫描报告里删** —— 白名单 tag 扫描里自然出现就保留进报告照常喂 GLM (**不主动去搜黑名单**); GLM **真推荐了 → 无视价格强制只进测试仓 (绝不真买), 状态标 `paper:黑名单强制` + 主页 `blacklist_paper` 事件流记一条**。实现四处 (都 import `tags.BLACKLIST_REPORT_MARK` 单一常量, 别硬编码): ① scanner `scan_by_tag` 不再 continue 丢弃 + `generate_tag_report` 在这些市场 slug 行尾打标记; ② auto_trader `_in_universe` 读标记, 在真买判定**之前**强制 route=paper (真买通道对它永远关着); ③ auto_discovery 数候选门槛时**扣掉**带标记的 (黑名单绝不单独把某 tag 顶过 5 个去触发一次 GLM 调用); ④ auto_discovery `/auto` 预演路由对黑名单显示 paper。口径沿用: **只看标题/slug, description 顺带提及不算**; 白名单覆盖 "tag 级黑名单" 保留 (保 Olympics-with-Sports-tag)。已持有的 bitcoin 仓照常管理。⚠️ 强制判定用**扫描报告标记** (scanner 按市场原始标题判) 而非事后拿 GLM 可能改写过的标题重跑 is_blacklisted, 避免 "fed rate" 这类带空格词在连字符 slug 里漏判 → 漏成真买。
14. **Kelly 本金冻结 (2026-07-11 用户拍板)**: `AUTO_KELLY_BANKROLL_REF=50` — 单仓金额永远按固定 $50 盘子算 Kelly (以后加现金 → **多开仓**, 不放大单仓); cluster 20% 上限仍按**真实**本金算 (现金越多房间越大; 月 DD 预算已于 2026-07-18 删除)。设 0=解冻回实时本金。sizing.py 一个字没改 — auto_trader._suggested_size 本地函数替代了内部 HTTP /api/suggested_size。
15. **信心乘数 (2026-07-12 用户拍板)**: GLM 的 confidence 参与金额 — high ×1.25 / medium ×1.0 / low ×0.75 (`AUTO_CONF_MULT_*` 可调), 只缩放 Kelly 那步的下注本金, 天数/冷门/cluster/DD/[$1,$15] 硬边界照旧夹 (high 冲不破 $15/cluster 顶, low 跌破 $1 就不下)。
16. **Politics tag 已删 (2026-07-12 用户令)**: 智谱内容过滤 3/3 轮必拦、白白报错 → 从 tags.py 白名单移除 (范围窄的 US Politics 保留); 定时扫描白名单现为 26 个 tag。
17. **q 校准移到 Python + 系数 0.5→0.8 (2026-07-18 用户拍板, 见 8.2.0)**: 旧 = DISCOVERY/REEVAL prompt 里让 GLM 自算 `市场价+0.5×(q_raw−市场价)` 把跟市场的分歧收到 50% (打五折)。新 = GLM 只给**原始真实 q_raw**, 校准挪到 Python 一处确定性做 = `市场价 + AUTO_Q_TRUST×(q_raw−市场价)` (`AUTO_Q_TRUST` 默认 **0.8** 信自己八成; =1.0 不校准 / =0.5 复现旧五折 / =0.0 纯跟市场)。单一来源 `modules/auto_calibrate.calibrate_q`, 选品 (`auto_discovery._normalize`) + 重评 (`auto_reeval._run_one` 方向纠错闸**之后**, 让翻转嗅探仍按原始数判) 都调它。GLM 原始值留档: 选品在 `raw_json`, 重评在 `raw_text`。sizing.py 照旧吃传入的 q (它"单层折扣 0.5 DISCOVERY"注释已过时但行为不变, 按隔离铁律不改)。⚠️ **2026-07-21 收口 (8.3.3): prompt 五折已物理删除** —— DISCOVERY/REEVAL prompt 里的校准整段删净 (`市场价+0.5×…`、所有"校准后 edge/估算"、REEVAL 的 A6/B3 校准步)。GLM **和手动贴Claude** (`/api/reeval_prompt` / `/api/paper/reeval_prompt` / 选品 full_prompt 共用同一 prompt) 现在**都只给原始估算、无任何校准** (用户明确"原始输出什么就是什么")。校准只在 Python `auto_calibrate` 做、**只自动链路调**; 手动流程没有 Python 这步 → 拿到的就是纯原始 q。原先 8.2.0 的"覆盖机器指令"已去掉 (prompt 里已无 0.5, 不用再防双重折)。prompts.py 因此成了 AUTO 分叉 (清单 #8), 同步老项目时必须重删五折。sizing.py 照旧吃传入的 q (注释"单层折扣 0.5"过时、行为不变, 按隔离铁律不改)。
18. **止损/重评再改 (2026-07-18 用户拍板, 见 8.3.0 / 分叉补丁7)**: ① **收敛型** 从最高价回撤 20%(≤3天12%)+连6拍确认 → **直接平仓**(不再交重评; 盘中也不做亏损触发重评)。② **事件型**: 亏 >50% 强行直接平仓(见 8.1.0); 盘中另 **任何盈亏水平、从"持有期最好点(最低亏损)"回撤 ≥5pp → 触发1次重评**(基线取最好点、触发后重置 → 单次暴跌只算1次; 涨回再跌5pp又触发; **无时间冷却**, 原6h+10pp作废); 重评说 exit **立刻卖**(exit护栏已删, 见 8.1.0)。③ **每天 15:00 全仓巡检重评对所有仓照旧**(独立路径 = 更新q/盈利仓往上改/兜底exit, 不是止损, 跟盘中触发是两条路)。④ **删 `cancel_autostop`** 决策选项(重评不能再"容忍继续亏、关止损"; prompt/schema 移除 + 执行中和为 hold); 手动"止损OFF"开关暂留。混合型不变(回撤35%直接平仓)。旋钮 `AUTO_REEVAL_RETRIGGER_DROP`(默认0.05)。⚠️ 事件型"任何水平5pp就触发"会明显增多重评 API 调用 — 用户明知选的。实现 monitor.py + auto_reeval.py, 同步老项目重做见分叉补丁7。
19. **三号账户 shadow「低价拿到底」(2026-07-24 用户拍板, 见 8.5.0)**: 同一套 GLM 推荐三账户跑三策略 (主策略 / bench 基准 / shadow)。shadow 规则死: ① 只吃 `status='paper'` 候选 (黑名单强制的不吃 — 黑名单永不真买铁律对任何真钱账户适用; ≥0.85 那半永远排除); ② 临下单新鲜 ask **≤0.40** (`SHADOW_MAX_PRICE`) 才买; ③ **$2/仓** 固定 (`SHADOW_USD_PER_POS`); ④ **止损不止盈**: 入场锚 **−60%** (`SHADOW_STOP_PCT`, 07-24 回撤研究定值: 唯一真赢家中途最深跌−55%、输家全奔零; −50% 会杀赢家) + $0.05 地板, 连3拍确认; 无止盈/无重评/无时间止损/无移动止损 — **拿到结算**; ⑤ 只买启用后的新推荐 (存量测试仓不补)。隔离与 bench 同套路 (SHADOW_POLY_* env交换第二实例 / 自带查仓查现金 / 同凭据守卫连 bench 也查)。`SHADOW_DRY_RUN=1` 空跑。

- ✅ **第1步 定时扫描** `modules/auto_scheduler.py`: 每分钟看钟; slot 标记存 app_state (`auto_scan_last_slot`) → 重启不重放、停机错过开机补跑; 扫描失败本 slot 不重试等下一个。实测: 27 tag 12s。
- ✅ **第2步 GLM 自动选品** `modules/auto_discovery.py`: 扫描完 → 只挑"报告里有 `### ` 候选"的 tag → 每 tag 一次 GLM (glm-5.2 + search_pro + thinking max, **跟手动贴 Claude.ai 同一份 DISCOVERY prompt + cluster 字典** + `JSON_APPEND` 机器指令) → `_extract_recs` 解析校验 (百分比归一/side白名单/坏数据剔除) → 入库 `auto_candidates` (带 route 预演标签) + `auto_discovery_runs` (tokens/错误/是否追问)。页面 **`/auto`**; 手动触发 `POST /api/auto/discover_now` (body 可 `{"tag":"Iran"}`)。**只列清单, 不买不进测试仓**。实测 (2026-07-08, Iran): 1 条推荐, 一次就给了 JSON, tokens 20421+8150; 推荐 YES@0.195 被正确标 🧪进测试仓。
- ✅ **第2.5步 24h 巡检重评** `modules/auto_daily_reeval.py`: maybe_run 由 auto_scheduler 心跳带动; slot=日期 (过了 DAILY_HOUR 算今天); **首次部署只上膛不补跑** (防部署当天突袭全仓); 逐仓串行 `save_auto_reeval_pending` + `auto_reeval.run_and_store` (force_manual=False = 离线自动执行/在线挂 pending)。手动触发 `POST /api/auto/reeval_sweep_now`。重评 GLM 路径实测: 51s 出合法决策 (update_q, 3 信源)。
- ✅ **第3+4步 分流执行+自动下单** (`modules/auto_trader.py`, 用户 2026-07-08 "全部自动现在开始"): 候选按**执行时刻新鲜盘口价**过 40~85 分流 → 真买走 内部HTTP `/api/suggested_size`(公式金额)+`/api/buy_position`+等同步+`/api/record_position` 自动录 meta; 测试仓走 `/api/paper/add`(auto_size, fallback $5)。所有跳过点名记 status (已持有/公式<$1/日限额/仓位满/无盘口/gamma查不到/已关闭)。手动触发 `POST /api/auto/execute_now`。定时链 = auto_scheduler: 扫描→选品→执行 一条龙。**E2E 实测 (2026-07-08)**: Iran YES@0.23→测试仓$1.94; 法国世界杯 NO (负险市场!) 公式$4.91→按步长买 5 股 $3.37 matched, meta/auto_trades/现金全对。
- **额度: 用户 2026-07-08 拍板【不要任何限制】** — 原 $10/天、8 仓上限是 Claude 擅自加的默认值, 用户原话"我从来没有说过这指令" → 已撤: `AUTO_TRADER_DAILY_CAP_USD=0` / `AUTO_TRADER_MAX_POSITIONS=0` (**0=不限, 现为默认**; 判断逻辑保留, 以后用户要限改 env 就行, **别再擅自加限额**)。台账仍按实际成交额照记。单仓金额天然由 sizing 公式管 ($1~15 + cluster 20%; **月DD预算 2026-07-18 用户拍板删除** — 18仓时$30打满全拒新单, env SIZING_MONTHLY_DD_BUDGET=999999 功能性删除, sizing.py 未动)。
- **其余护栏 (用户认可保留)**: `AUTO_TRADER_MAX_DRIFT_PP=3` 临下单漂移容差 (用户拍板) / `AUTO_TRADER_CANDIDATE_TTL_H=24` 候选保鲜期 / `AUTO_FORCE_OFFLINE=1` 永远按离线跑 (重评决策自动执行, 开页面看盘不暂停自动化 = presence 旗标已落地)。
- ✅ **2026-07-08 全代码审查修复 (16 项, 用户逐条拍板/授权)**: P0×3 = 方向更正后 exit 二次确认 / 无档案仓不重评+红警 / 临下单 3pp 漂移复核+录档重试3次(cluster_id 无'-'置空防拒)。其余: 台账记实际成交额(解析"≈ $X.XX") / 轮内(slug,side)去重+买后即记已持有 / **防对锁**(已持同市场对面方向拒买) / trader+discovery 并发锁 / 候选 24h 过期 / paper 同 token 去重 / 追问语义扩展 / 宇宙闸门反引号精确匹配 slug / record 键名修正(slug/original_confidence, 信心值不再丢) / 启动时两把 key 隔离自检+ANTHROPIC_API_KEY 告警。详见 git log 2026-07-08。
- ✅ **原"未定规则"四件 2026-07-08 用户全部拍板**: ① 熔断线 = **不要** (亏损不设限, 以后要了会说) ② 通知渠道 = **不做** (红色警示 + 主页事件流足够, 用户自己定期看) ③ watchdog = **不做** (用户自己定期看盘) ④ GLM 挂了 = **Claude 兜底** — `.env` 配 `ANTHROPIC_API_KEY` + `AUTO_REEVAL_PRIMARY=glm` + `AUTO_REEVAL_DUAL=0` (GLM 主用, **仅 GLM 失败那次才调 Claude**, 平时零 Claude 花费; autobot 启动自检编排配错会大声警告)。
- ✅ **GLM 深度升级 (2026-07-09 用户拍板)**: ① **多轮自主搜索 agent** `modules/auto_glm_agent.py` (像 Claude 一样搜→想→再搜: web_search 做成函数工具循环调用, 上限 8 次×15条/次, REST /v4/web_search; **任何失败自动回退老的一次性注入搜索**, `AUTO_GLM_AGENTIC=0` 整体关闭) — 选品和重评都走它。② 旋钮拉高: 输出 32K→**65536** (昨天 Primaries 撞过 32K 顶), 回退注入搜索 20→40 条, 温度 0.6→**0.3** (分析要专注; 用户口述"调高"按意图=调优)。③ 用户明确**不要**: 自我批判二遍 / 同题双跑取交集。实测: REST 搜索 15 条秒回 (50 条会超时, 别调过头); Iran 单 tag agentic E2E 见 git log。

## 账户凭据状态 (2026-07-08 深夜 — 已全部打通 ✅)

- **新账户 = Polymarket 2026 新架构「存款钱包」账户, 必须 `POLY_SIGNATURE_TYPE=3` (POLY_1271)** — 这是折腾一下午的最终答案: 用户的 funder(profile URL 地址)和导出私钥**从头到尾都是对的**, 但 sig=1/2/0 一律余额$0 + 下单报 `maker address not allowed, please use the deposit wallet flow`。sig=3 一切通 (余额/下单/卖出)。老项目账户是老架构 (sig=1) 被豁免, **别拿老账户的经验套新账户**。
- **py_clob_client_v2 已升 1.0.2** (vendored 目录已替换; 1.0.0 不会给 sig=3 填正确的 order signer → 报 `order signer address has to be the address of the API KEY`)。参考: [py-clob-client-v2 issues #51-53](https://github.com/Polymarket/py-clob-client-v2/issues/51)。
- **新 CLOB 金额规则**: 市价买单 maker 金额 (size×price) 最多 2 位小数 → executor.buy 已打 AUTO 分叉补丁 = **整数股数** (不足 $1 最小单向上凑)。这是本仓库对同步模块 executor.py 的**唯一有意分叉**, 同步老项目代码时**必须保留**。
- 链上验证是死路: Polymarket 现金是内部托管, **连老账户的 $76.85 在链上都查不到** (proxy 合约都没部署), 唯一真相源 = CLOB `get_balance_allowance`。
- POLY_API_KEY/SECRET/PASSPHRASE 不用填 (私钥现场派生, "Could not create api key" 400 后转 derive 是正常日志)。
- ✅ **真钱闭环测试完成 (2026-07-08)**: 美伊核协议 NO 2股@0.89 buy(bot API) → record_position meta → GLM 重评(R key, id=2 出合法 update_q + 高质量调研) → force_exit 0.885 卖出 → closed_positions 记账/meta 清零/现金复原 全对。全程磨损 ~3 分钱。

## AUTO 分叉补丁清单 (对同步模块的有意修改 — **从老项目同步代码时必须保留这些**)

1. **executor.py**: ① buy 的 size 凑步长数学 (maker=size×price 必须 ≤2位小数; step=10/gcd(价格千分位,10), 病态凑不出→拒单) ② `_order_options_for_token` 按 token 自动查 negRisk+tick_size (gamma, 进程内缓存, buy+sell 都用 — 负险市场已实测成交) ③ 买单成功消息修正 (v2 makingAmount=USDC, takingAmount=股数, 老代码标反)。
2. **auto_reeval.py**: ① GLM_JSON_INSTRUCTION 的 new_q 行硬化 (明示持有方向, 举例) ② `_confirm_new_q_direction` 方向嗅探+**反问 GLM 本人**守卫 (用户 2026-07-08 规则: 全自动不甩给用户; 疑似翻转→追问一条只要 `new_q_held_side`; 确认不了→本轮按模型失败=不动仓)。嗅探规则 `_nq_flip_suspect`: 离参考q >0.35 且镜像 <0.15。实测案例: 持NO q0.93 被填 0.10。 ③ 同函数内 **exit 二次确认** (审查①): 数字被更正≥0.05 且 action=exit → 再追问 `final_action` 按最终答案执行, 拿不到=放弃; 附带 side 取值兼容 pos["side"] (executor 归一化仓位没有 "outcome" 键)。 ④ `run_and_store` 入口**无档案闸** (审查②) ⑤ `_build_prompt` 支持 `pos["_trigger_note"]` 注入触发原因 (反向推荐触发重评用, 2026-07-10): meta 无 side → 不评, 建议行标 error + 🔴 `no_meta_alert` 事件, 等用户补档案。 ⑥ **q 校准 (2026-07-18 起, 2026-07-21 收口, 见规则17 + 分叉#8)**: prompt 五折已物理删除 → GLM 自然给原始 new_q; `_run_one` 在方向纠错闸**之后**调 `auto_calibrate.calibrate_q(new_q, cur)` = 市场价+0.8×(raw−市场价) 再存/执行 (GLM_JSON_INSTRUCTION 的 new_q 行只留一句"给原始判断、不校准"提示, 不再是覆盖)。
3. **tags.py**: ① `is_blacklisted` 关键词黑名单前置 (只看 question+slug; 2026-07-10; tag 级黑名单仍被白名单覆盖)。② `BLACKLIST_REPORT_MARK` 常量 (2026-07-12): 黑名单市场在扫描报告 slug 行尾的标记文案, scanner 写 / auto_trader+auto_discovery 读 —— 三方全靠 import 这个常量, 改文案只改这一处。
4. **db.py get_presence**: `AUTO_FORCE_OFFLINE=1` (默认开) → effective_online 永远 False = 重评决策自动执行, 开页面不暂停自动化。设 0 恢复老行为。
5. **scanner.py (2026-07-12 黑名单改口径, 见规则13)**: ① `scan_by_tag` 提取 markets 时**不再 `continue` 丢弃**黑名单市场, 改为 mkt_obj 带 `blacklisted` 标志保留进流水线。② `generate_tag_report` 渲染 slug 行时黑名单市场追加 `BLACKLIST_REPORT_MARK`。同步老项目 scanner.py 时**必须重做这两处** (老项目是硬 continue 丢弃, grep `blacklisted` 验证); 另注意 scanner 的动态 tag 合并/解析拆除处照旧 (见规则8)。
6. **event_driven 出场大改 (8.1.0, 2026-07-18 用户最高指令) — 动三个文件**: ① **monitor.py**: 新常量 `EVENT_DRIVEN_HARD_STOP_PCT=0.50` + `_evaluate_position` 里 `(a2)` 分支 —— 事件型跌破成本 **-50% → 直接平仓 STOP_LOSS**, 排在 $0.05 地板之后、其余所有止损线/重评/手动关止损**之前**, 任何东西越不过 (原"-60%→PENDING_REEVAL 交重评"作废; `STOP_LOSS_PCT_BY_TIER['event_driven']=0.60` 只剩 legacy/未分类支线引用)。② **auto_reeval.py `_auto_execute`** + **dashboard.py 确认路径**: 都删掉 `guard_event_driven_exit` 调用 (原需 `thesis_broken` 或 `edge≤-EXIT_GUARD_EDGE(0.08)` 才放行 exit, 否则降级 update_q) → **GLM 判 exit 立刻执行**。`guard_event_driven_exit` 函数体保留但**已无调用处** (死代码, 别当残留删)。⚠️ 方向纠错闸 `_confirm_new_q_direction` (item 2 的 ②③) **保留不动** = 仍防 GLM 把胜率数字填反卖错边。同步老项目 monitor/auto_reeval/dashboard 时**必须重做这三处** (grep `EVENT_DRIVEN_HARD_STOP_PCT|guard_event_driven_exit` 核对)。
7. **止损/重评再改 (8.3.0, 2026-07-18 用户拍板) — 动 monitor.py + auto_reeval.py**: ① `_evaluate_position`: `_direct_stop = tier in ("convergent","hybrid")` (收敛也砸穿直接平仓; `PENDING_REEVAL` 退役)。② `_maybe_trigger_auto_reeval` **重写**: 只对 event_driven; 任何盈亏水平, 从"持有期最好点(最低 loss_pct, `get/set_reeval_watch_loss` 存)"回撤 ≥ `RETRIGGER_DROP_PCT`(0.05) → 触发并把基线重置到当前 (单次暴跌只算1次; **无 6h 冷却**); convergent/hybrid `return` 早退 (不盘中重评)。③ auto_reeval: `RETRIGGER_DROP_PCT` 默认 0.10→0.05; prompt/schema 删 `cancel_autostop`, `_auto_execute` 的 cancel_autostop 分支中和为 hold (不置 autostop_disabled)。每天 15:00 全仓巡检 (`auto_daily_reeval`) 对所有仓照旧不动。同步老项目 monitor/auto_reeval 时**必须重做这几处** (grep `_direct_stop|RETRIGGER_DROP_PCT|cancel_autostop` 核对)。
8. **prompts.py (2026-07-21 用户拍板, 见规则17)**: `DISCOVERY_PROMPT` + `REEVAL_PROMPT` 里的"打五折"校准 (`市场价+0.5×(q_raw−市场价)` + 所有"校准后 edge/估算" + REEVAL 的 A6/B3 校准步 + `build_reeval_prompt` 的"未校准"字样) **整段删除** → GLM/手动贴Claude 都只给**原始估算** ("原始输出什么就是什么", 用户 2026-07-20 令)。校准改在 Python `auto_calibrate` 做 (只自动链路)。同步老项目 prompts.py 时**必须重删这些** (老项目仍有五折; `grep 校准|q_calibrated|市场价 + 0.5` prompts.py 应为 0)。

## 已知小坑 (无害, 记档)

- ~~日限额按"下单请求金额"记账~~ → **2026-07-08 审查已修**: 现按实际成交额记 (从 buy 消息解析 "≈ $X.XX", 解析不到退回请求额)。
- 老监控守卫日志 "positions=[] AND cash=0 (likely API failure)" 在空账户期每 30s 一条 — 有钱后自动消失。
- buy 的最小单凑整可能小幅超花 (请求 $1 极端可成交到 ~$3, 有 +max($2,75%) 上限拒单保护) — 用户未要求收紧, 保持。
- monitor 启动横幅还写 "hybrid → 入场锚 -35%" (7.4.4 实际已是移动止损) — 同步模块内纯文案, 按铁律不碰, 下次同步老项目自然带新。
- 调度器单线程串行: 09:00 扫描+选品+执行若拖过 10:00, 巡检会晚点补跑 (不丢)。
- 黑名单改口径后 (2026-07-12): 黑名单市场现在也进订单簿检查的 first-50 名额 (以前早早被 continue 丢了不占名额)。极busy的tag (>50 合格 market) 尾部个别正常 market 可能被挤出不做订单簿检查 → 不进报告。实际影响很小 (多数 tag 远不到 50; 白名单里黑名单命中本就少), 未处理, 记档。

## 运行

- venv: 本目录 `.venv` (python3.12, base=/opt/homebrew/opt/python@3.12; **httpx 必须带 h2**, requirements 已 pin)。
- `py_clob_client_v2` **不从 pip 装** — vendor 在仓库根目录 (Polymarket 官方 **1.0.2**, 附 LICENSE; 1.0.0 不支持 sig=3 正确签名, 别降回), autobot.py 从项目根运行自动 import 到。
- **重启 = `bash /Users/baymaxagent/polymarket-auto/restart.sh`** (固化了 LISTEN-only 端口杀 + 正确入口, 别手敲)。
- `.env` 必填: `POLY_PRIVATE_KEY` (Polymarket 设置里导出的) / `POLY_FUNDER` (profile URL 里的 0x 地址) / **`POLY_SIGNATURE_TYPE=3`** (新架构存款钱包; 老式账户才是 1/2) / `ZHIPUAI_API_KEY_DISCOVERY` / `ZHIPUAI_API_KEY_REEVAL` / `DASHBOARD_PASSWORD` / `FLASK_SECRET_KEY`。缺 POLY_* 只读不能交易; 缺智谱 key 对应功能自动跳过 (不报错)。
- 数据库 `v4.db` 本目录独立空库 (首启自建); 新增表 `auto_candidates` / `auto_discovery_runs` 由 auto_discovery 自建 (CREATE IF NOT EXISTS, 不动 db.py)。
- 页面: 主页 `:5052` = **全自动监控页** (`modules/auto_dashboard.py` 独立新文件, 2026-07-12 上线: 资产曲线在顶、按天战报只展开当天、完整只读重评建议、事件中心三榜、操作记录全事件流、警报/持仓/选品/应急停止; `/monitor` 同页稳定 URL; 聚合接口 `/api/auto/monitor`; 老半自动 `/panel` `/api_reeval` 已下线 302 跳回 `/`, dashboard.py 一个字没改) + **`/auto` 候选清单** + `/paper` + **`/history` 折叠版** (`auto_history.py` 覆盖: 仓位卡默认折叠, dashboard.py 未改) + `/m` 照旧。

## 沿用的关键设计 (fork 时代码已含 + 已同步 7.4.4, 不要改回)

精简自老项目 CLAUDE.md; 完整背景在老项目 `技术报告.md` (未拷贝, 需要时去那边**只读**查):

- 止盈/止损判定用 `pos.avg_price` 不用 `meta.entry_price`; 止盈触发价用 `get_best_bid()`, 止损用 `cur_price` (不对称是故意的, 防低流动假象/瞬时蒸发)。
- 三档止损 tier (收敛/混合同步老项目 7.4.4; **事件型 AUTO 8.1.0 分叉**): **收敛+混合都是移动止损** = 从持有期最高价 peak_price 回撤 (收敛 20%/≤3天 12%; 混合 35%) + 连 6 拍确认; **事件型 = -50% 强行止损【直接平仓】(AUTO 2026-07-18 用户最高指令; 原 -60%→重评作废) + $0.05 地板**; 未分类默认当 hybrid (无 legacy 档)。**AUTO 8.3.0: 收敛+混合砸穿一律直接平仓** (`_direct_stop=tier in (convergent,hybrid)`; 收敛原"→PENDING_REEVAL 交重评"作废, PENDING_REEVAL 退役); **事件型 exit 护栏 `guard_event_driven_exit` 已删** (重评判 exit 立刻执行, 见分叉补丁6/7)。事件型盘中重评改由"从最好点回撤5pp"触发 (见规则18 / 分叉补丁7)。
- 止盈 (老项目 7.4.1/7.4.2): 事件型 **翻倍 (2×avg) 先到全卖**, 否则 0.92 卖一半; 卖半后的后半跌破 0.782 (=0.92×0.85) 触发保护全卖; 收敛型 ≤3天 0.88; 其余 0.90 或 +100%。
- 重评: GLM 主用 (glm-5.2 + search_pro + thinking max, `_glm_regex_extract` 正则兜底**别删**); 决策 **3 项 hold/update_q/exit** (`cancel_autostop` 已删=8.3.0); 离线自动执行 / 在线挂 pending; `force_manual=True` 永远等手动确认。重评 prompt 喂"大跌前中枢" `_pre_dump_center` 反锚定。
- SQLite WAL + busy_timeout; 时区一律 aware UTC; 卖出必写 `closed_positions`, 且**只在完全平仓时写** (部分卖出不写, 防假平仓)。
- DNS guard (`gamma_client.install_polymarket_dns_guard`) **不删** — 本机对 *.polymarket.com 有间歇性 DNS 污染, 删了全 bot 静默瘫痪。
- Gamma 查已结算市场必须显式 `closed=true`。
- `/m` 手机页只读; `/paper` 测试仓 🔒 绝不调 executor.buy/sell、绝不调付费 API。
- Dashboard 鉴权按 Host 头: localhost/127.0.0.1 直通, 其余要密码; 登录限流持久化 db。
- sizing: `position_size_usd()` 1/4 Kelly + cluster cap, 硬边界 [$1,$5] (2026-07-23 上顶 15→5), env `SIZING_*` 可调 (第3步真买金额 = 这个计算器)。~~月 DD 预算~~ 2026-07-18 用户删 (env=999999)。
- `modules/version.py` = **AUTO 独立版本线** (现 **8.0.0**, 2026-07-12 从老项目 7.x 分家; 详见「版本号规则」)。启动日志动态读它; 改版本必按「版本号规则」同步全部文档。

## 约束 (继承老项目)

- shell 是 zsh: 命令行不要裸 # 注释; 中文注释避开 zsh 误解析; macOS 没有 `timeout` 命令。
- 改 SQLite schema 前先 `cp v4.db v4.db.bak_$(date +%s)`。
- 不碰 launchd/systemd; 启动只用 restart.sh。
- 改完代码: 先 import 冒烟测 → restart.sh → `tail bot.log` 确认无报错 → 才算成功。
- 不修改老项目和 v3 的任何文件。
