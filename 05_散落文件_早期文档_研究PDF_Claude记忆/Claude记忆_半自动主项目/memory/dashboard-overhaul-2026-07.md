---
name: dashboard-overhaul-2026-07
description: "20项 dashboard/策略大改清单 + 已锁定spec + 进度 (2026-07-05 起, 分批做, 改前问清)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 80767cb3-3d97-4b57-bdf2-c73b9ce18408
---

用户 2026-07-05 给 20 项改动清单, 要求: 分组、从简单到复杂、一批批做、改前问清、不要搞乱。已批准"先把前3波做了"(= 下面 8 项已锁定, 开做)。相关: [[auto-reeval-pending-changes]] [[paper-trading-feature]]。

## 已锁定 spec (前3波 8 项, 用户已批准开做)
- **#1 版本号**: 单一 VERSION 常量 (起点 **7.1.3**), major.minor.patch 三级: 整数=**需用户审批**; 小数1位(minor)=重大更新**我自己改但必须告知用户**+详细记入技术报告, 同时上N个大功能就+N不打包成一次; 小数2位(patch)=小改**我自行决定不用审批**, 技术报告记关键词即可. 网页/手机/日志/GitHub 全同步. 规则写进 CLAUDE.md.
- **#7 事件中心实时榜**: 现 30m/1h → 并排加成 30m/1h/6h/1d.
- **#15 右上按钮**: 拆"页面导航"vs"操作". 操作行移到 总盈亏/持仓数/总投入/资产组合 那栏**下面新起一行**; **删**[检查持仓][刷新]; **留**[停止](红色); 移下来[在线/API开关][控制台][监控中]; 各按钮**不同色**美化; 响应式: 小屏先缩小恐龙→放不下就隐藏恐龙(**不删**), 主按钮**绝不重叠**.
- **#2 资产曲线**: ①渐变填充+顺滑+配色 ②悬停tooltip看每天数值 ③标买卖点 ④成本线+盈亏区上色. 四项全做.
- **#14 /history 卡片**: 改**长方形、放大、每张多放信息、少浪费空间**; 字体/配色/关键数字放大 + 多加图表.
- **#6+#5 持仓页拆3 tab**: **当前持仓**(只看,放大,信息+止损+保存等只显示有颜色不可操作) | **重评操作**(新,所有按钮搬来 + #5 重评结果粘贴填入一键应用) | **重评模式**(现有复制prompt,不动). tab顺序: 当前持仓|重评操作|重评模式.
- **#3 自动重评建议**: 放超过 **2天(48h)** 自动清空 (status=cleared).
- **#17 手机版/m**: 加"**最新2个往期仓位监测卡片**"(只看). 不破 /m 只读铁律.

## 第4波 (2026-07-05 澄清)
- ✅ **#20 在线/离线 bug 修好** (7.2.3): 症状=该离线时一直在线。根因=前端 `mousemove` 太敏感(鼠标微动就 ping 刷 presence_at, idle 攒不到阈值)。修: 主页+副屏活动监听去 mousemove(只留 scroll/click/keydown/touchstart); 阈值 30min→10min 弹窗(IDLE_MODAL_SEC/P_IDLE_MODAL_SEC 1800→600)+ PRESENCE_STALE_MIN 35→12 硬兜底。server 逻辑本就对。已实测 idle 能正常累积(修前卡 176s, 修后涨过 600s)。
- ✅ **#9 已给用户解释 cluster** (=相关性簇, 会一起赢/输的仓归一组, 风控用, 命名 话题-方向, 限同簇≤20% bankroll). 用户之前忘了 cluster 是啥; **用户 2026-07-06 定: cluster 不升级** (#9 关闭, 无代码改动).
- ✅ **#4 第一版做完** (7.2.4): `/api_reeval` 美化 + 顶部"智谱 vs Claude 总揽"(前端从 compare_json 算: 动作一致率/平均q差/最大q差/论点一致率 + 各自动作分布); 每卡片头部加「✓/✗ 一致 + q差」徽章. **真数据**: 10条里5条双方都成功 → 一致率40%/平均q差15.4pp(智谱跟Claude分歧不小). 总揽第一版后**用户要求加3字段并已加** (7.2.5): 智谱失败次数/谁更激进保守(exit/hold/cancel各模型)/平均信心对比. 真数据洞察: 智谱失败2次(Claude也失败3次)、Claude更爱cancel扛单(2次)智谱更爱hold、平均信心都=中. #4 基本完成(除非用户再调).
- ⬜ **#18 延后** (用户: 继续留列表里先不管).

## 最难波 (2026-07-06 起, 用户选先做 A=统计分析)
- ✅ **#9 cluster 不升级** (用户定).
- ✅ **#8 统计分析大改 完成** (7.3.0 minor): 用户要 ①可视化 ②检查所有指标 ③新角度 ④实时更新. 做了: 审计现有指标(口径全对, 校准2小局限非bug) + `db.get_history_extras()`(时间趋势按月累计/卖飞=(final_outcome-exit_price)*size/盈亏分布4桶/按出场方式`_exit_category`归类) + /history 加 Chart.js(趋势柱+累计线/分布柱)+卖飞3卡+出场方式表+每60s自动刷新. **洞察**: 止盈11笔100%赚+$25 / 重评清仓14笔亏-$8.6(实锤割肉) / 卖飞净$42. 65笔BACKFILL单列. **第一版, 用户看完可能迭代**(颜色/更多角度/布局).
- ✅ **closed_positions 数据修正** (7.3.1, 用户发现跟 Polymarket 对不上): 对账=98唯一token(80平+18持有), 旧表100行/85token 两套口径混+5假平仓. `scripts/rebuild_closed_positions_2026_07.py` 按 Polymarket /activity 重建成80行(保留元数据), 全对齐(赚最多5笔/累计-$3.51). **根因守卫已加**(7.3.2): monitor check_once 只在 `pos.size-sell_size<0.01` 全卖时才写 closed+清meta. **但重大发现: 当前 monitor.py 根本没有 take_profit_half/partial/half —— v7.0 文档写的"卖一半"实际代码里没有!** 全是 sell_size=size 全卖. 守卫对当前=no-op纯防御. 跟"缺Executor import"同现象=**monitor.py 被改残, v7.0 出场策略(卖一半/收敛移动止损/事件exit护栏)可能没在代码**. ⚠️ **待办: 核对 v7.0 出场策略 文档vs代码**. closed_positions 漂移主要来自"重入"(平了又买回), 少见, 重跑 `scripts/rebuild_closed_positions_2026_07.py` 即可再同步.
- 🔴 **v7.0出场+GLM+双模型 曾被回退, 已恢复** (7.3.3): 核对发现 monitor.py+auto_reeval.py 在 commit `6561636`(2026-06-26 12:00 auto-backup) 整体回退到老版本(`git log -S` 证实 TAKE_PROFIT_HALF/TRAILING_STOP/_pre_dump_center/_run_glm/run_reeval_dual 全被删) → 十天里 bot 跑老 v5.x 出场(启动日志却撒谎说v7.0). 从 `6561636^` 恢复(auto_reeval 221→731, monitor 501→663)+补 autoclear. 备份 .bak_pre_v7recover_*. ⚠️⚠️ **根因未明**: 什么覆盖成老版本不知, 可能再犯, 只这俩被回退(dashboard/db没事). **每次开工先 grep 确认 monitor 有 TAKE_PROFIT_HALF、auto_reeval 有 run_reeval_dual**(没有=又被回退了). ✅已 git 提交+push锁定(7679fb5). **根因已查明 (2026-07-06): 用户 VS Code SSH 编辑, monitor.py+auto_reeval.py 长期开在标签页(旧v5.13缓存), 某次保存/重连把旧缓存写回磁盘覆盖了v7.0 → auto-backup提交固化. 只这俩被回退=只这俩开在VSCode标签. v3(polymarket-semi-auto)已排除(232行无TAKE_PROFIT_PRICE, 无auto_reeval).** 防: 用户别长期开这些文件/看到"文件已在磁盘更改"选Revert/改完Reload Window/关workspace auto-save. ⚠️ 若再发现被回退, 从 git 最近的完整版本(grep TAKE_PROFIT_HALF)恢复即可.
- ✅ **#16 测试仓 /paper 大改 完成** (7.4.0 minor): 用户要"像真仓有生命周期"——进行中区只显示 open且未would_sell; 一"卖"就移历史. `/api/paper/list`只返进行中; 新`/api/paper/history`=已卖/清空/结算+最终模拟盈亏+**最高点peak(本可赚, 哪怕后来亏到底)**+预测准不准判定+统计(模拟赚钱率/结算对率/总盈亏). PAPER_HTML加统计区3卡+往期区. peak_price monitor早在记, 这次显示. 🔒全只读. 真数据:历史10仓总$+5.6, 有仓最高本可赚$13.49最终-$3.75.
- 🟡 **#10-13 策略波 (真钱, 摆现值让用户定)**: **#13 搜索%现价**(标准8-92/中5-95/大3-97)用户看完**决定不改**. **#12 edge门槛**(v7.2: 标准6/中8/大10 基础 + 价位叠加±3 + 硬地板5, 在prompts.py)用户看完**决定不改**. **#10 止盈 ✅完成**(7.4.1): 用户问出真钱缺口——事件型0.92卖半后留的后半只有$0.05地板+(-30%)重评兜底会坐过山车. 加 `TAKE_PROFIT_HALF_PROTECT` 分支: event_driven且已tp_half_sold且best_bid<0.92×0.85=**0.782** → 全卖后半锁利润(直接卖不走重评, 常量`TAKE_PROFIT_HALF_PROTECT_DROP_PCT=0.15`). 另答清: TIME_STOP=距结算≤2天且价漂移<5pp才清("僵尸仓", 非止盈止损). **#10 续 ✅(7.4.2): 用户要"翻倍vs0.92卖半比谁先到"** → 1a最顶加事件型+100%全卖分支(未卖半时判): 低价入场<$0.46 → 2×avg<0.92 → 翻倍先到全卖落袋; ≥$0.46够不到翻倍 → 到0.92卖半. 卖半后留的半仓不再被+100%秒卖(tp_half_sold已置, 靠0.782保护跑结算). 1b改成只管非事件型. 自测$0.40→$0.80全卖/$0.48$0.50→0.92卖半. **#11 止损 ✅完成(7.4.3)**: (a)事件型加 -60% 入场锚%止损(`STOP_LOSS_PCT_BY_TIER["event_driven"]` None→0.60, 很松; _evaluate_position (b)段去掉`tier!="event_driven"`排除→走入场锚; 砸穿→重评+护栏, $0.05地板仍兜底); (b)确认拍已是30s/拍(6拍=3min防抖, 不改); (c)消灭未分类=monitor两处`tier=...or"hybrid"`(_evaluate_position L134 + _maybe_trigger L466)+前端tier下拉空白档改disabled+标签更新(事件-60%+地板). STOP_LOSS_PCT_LEGACY弃用. 现有5仓全已分类. 自测:事件亏62%砸穿/亏50%持有/未分类当hybrid亏40%砸穿. **🎉 20项dashboard + 4项策略(#10止盈✅/#11止损✅/#12edge不改/#13现价不改)全部收官.** **续 7.4.4 (用户加): 混合型止损也改成移动止损** —— 从"对成本价固定-35%"改成"从最高价回撤≥35%+连6拍确认"(跟收敛型同形式). 新常量`TRAILING_STOP_PCT_HYBRID=0.35`; _evaluate_position (b)段 `tier in ("convergent","hybrid")` 都走trailing, 只event_driven留入场锚-60%; 重评未启用硬卖fallback带hybrid回撤口径. `STOP_LOSS_PCT_BY_TIER["hybrid"]=0.35`保留(只给自动重评触发线-30%用). 自测混合回撤35%砸穿/31%持有. 启动日志+tier下拉标签+CLAUDE+技报中英+PPT(v7.4.4)全同步. **git已提交锁定(772d63c代码/5f8c3da+869c3d1 PPT), 推送dev.**

## 最难的一波 (最后做, 都还没问细节)
- #8+#19 /history 统计分析大改 (用户原话: 统计分析问题非常大, 要改的很多)
- #16 测试仓历史大改 (信息显示等一起大改)
- #10 止盈 / #11 止损 / #12 搜索edge / #13 搜索%现价规则 (真钱, 需精确数值)

## 进度
- (2026-07-05) 清单锁定, 前3波开做中。
- ✅ **#1 版本号** 完成 (v7.1.4): 单一源 `modules/version.py:VERSION`; dashboard 两处 nav 用 `{{ ver }}` + main.py 日志用 VERSION; 规则写进 CLAUDE.md「版本号规则」+ 技术报告中英. 起点 7.1.3 → 这批 patch 到 **7.1.4**.
- ✅ **#7 事件榜 6h/1d** 完成: 主榜按钮 30m/1h/6h/1d; 后端 `realtime_movers` `_RT_CFG` 按档换 interval/fidelity (30m/1h不变, 6h→interval=6h fid=30, 1d→interval=1d fid=60). 实测4档 change_pp 各不同. (手机版movers仍30m/1h, 未动=符合范围.)
- ✅ **#3 自动清空48h** 完成: `db.autoclear_old_auto_reeval(hours=48)` (status!='cleared' 且 created_at>48h → cleared, 数据不删); monitor run_loop 每心跳调.
- 🐞 **顺带修**: monitor.py HEAD 版本**缺 `from modules.executor import Executor`** (被某次编辑删+auto-backup提交, 老进程内存里还有所以没暴露), 我重启才崩 (NameError line63). 已加回. **教训: 重启前先 py_compile + 起一次确认, 别假设 HEAD 能跑.**
- ✅ **#17 手机版往期卡片** 完成: /m 加"最新往期仓位"区(最近2个, 只看), 复用 `/api/history/in_progress` + loadMHist(), 复用 .pcard 样式; footer 版本改 `{{ ver }}`. 不破只读.
- ✅ **#2 资产曲线美化** 完成 (Chart.js): ①渐变填充(gProfit/gLoss CanvasGradient)+tension0.35+新配色#22d3ee ②悬停tooltip(资产/成本/买卖详情, 分datasetIndex) ③买卖点(scatter三角: 绿▲买/红▼卖, `_interpY`落到曲线, /api/trade_markers 新接口=closed_positions entry_at/exit_at) ④成本线(total_cost+cash 虚线)+ fill{target:1,above绿/below红}盈亏区. db.get_portfolio_history 补 total_cost 列.
- ✅ **#14 /history 卡片** 完成 (纯CSS): .sell-cards-wrap 改 grid minmax(440px) 宽长方形填满; .sell-card 去 min/max-width + 字体11→12.5 + padding放大; .sc-grid 改 auto 1fr auto 1fr 双列键值(横向用空间, <640px回单列); 各子字体放大.
- ✅ **#15 右上按钮** 完成: nav `.nr` 整块删除(移下); `.ctrls` 加 `.op-row`(flex-wrap绝不重叠): 停止(红.opbtn.stop)/控制台(紫.panel)/API(青.api,JS paused时转红内联)/在线(.pres,JS online转绿)/监控中(.lp)/30s(.rb); 删检查持仓+刷新; `@media` 恐龙 <1120px缩<860px隐藏(不删). apimode-btn/pres-btn 靠ID被JS控, 移位不坏(已验证各1个).
- ✏️ **#2 后续调整 (7.1.6, 用户要求)**: **删掉买卖点三角标记**(用户觉得乱) —— loadChart 回到 2 数据集(资产总值+成本线), 去掉 _interpY/scatter/marker tooltip 分支/trade_markers 前端调用。`/api/trade_markers` 接口留着但已不用(dormant)。**成本线+绿红盈亏区 用户明确要保留**(已给他讲清: 成本线=持仓成本+现金, 资产线=持仓现值+现金, 差=持仓浮盈亏)。
- 📌 **版本**: 7.1.4 → 7.1.5 → **7.1.6** (patch, UI批次+删三角). CLAUDE.md 已记(技术报告中英停在7.1.5, 下checkpoint补). 计划: #6 完成=前3波收官 → 那时 minor bump 7.2.0(新操作tab=新能力) + 详记.
- ✅ **#6+#5 持仓拆3tab** 完成 (7.2.0, 最稳法=现有面板原样改名+新建只看面板): 
  - 「当前持仓」= 全新只看面板, 放**最前**(吃 updatePositions 第一匹配实时价, 顺带修好之前 cluster 行在前导致当前面板实时价失效的老问题); 用 `.pos-row` 但**无 data-slug** → cjApplyPos(`.pos-row[data-slug]`) 只认操作面板不冲突; q/信心/止损/决策状态纯文字; 止损OFF 用无id span, ar-light class-based.
  - 「重评操作」= 原 `pos-panel-current` 整块**改名 `pos-panel-ops`+default display:none, 内容零改动**(所有编辑控件tp-/conf-/tier-/sl-btn/newq + 加仓/清仓/API重评/止盈止损开关 + reeval-panel 全在) → **真钱按钮零风险**; reeval-panel 加 #5 粘贴框 `applyReevalJson`(按 action: update_q→改q/hold→维持/exit→reevalExit弹确认/cancel_autostop→toggleAutoStop; 复用现有 handler).
  - tab顺序 当前持仓|重评操作|重评模式|Cluster; switchPosTab panels 加 'ops'.
  - 验证: ID零重复(tp-0/conf-0/tier-0/sl-btn/slbadge 各1)、真钱按钮各5、view面板0输入框0按钮、#5粘贴框×5、只看面板真只读.
- 🎉 **前3波 8 项全部收官** (#1#3#7#2#14#15#17#6+5). 版本 7.1.6→7.2.0 (minor)→**7.2.1** (patch: 只看面板美化=q/信心/止损彩色chip+整体放大+盈亏加大+删q/p/edge冗余+删「切重评操作」提示, 全圈 `#pos-panel-current`). ⚠️ **版本号待用户定**: 本波有 #2+#6 两大功能, 按"+N"规则严格该到 7.3.0; 我暂作一次 overhaul release=7.2.0, 已在报告问用户要不要改 7.3.0.
- 📋 **后续波次待办** (还没问细节): #4 测试流程+API美化 · #9 cluster升级 · #20 在线/离线bug · #18 往期分析 · [最难] #8+#19 统计分析大改 · #16 测试仓历史大改 · #10#11#12#13 策略(真钱).
