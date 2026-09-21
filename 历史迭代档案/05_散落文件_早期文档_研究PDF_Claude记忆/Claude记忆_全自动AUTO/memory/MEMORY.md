# Memory Index

- [第3/4步已上线+永远离线+宇宙闸门 (2026-07-08)](pipeline-steps34-live-2026-07-08.md) — auto_trader 真钱自动交易激活; AUTO_FORCE_OFFLINE=1; E2E 体育误买事故与白名单闸门由来
- [流式"扫一个喂一个"4路并发+即时下单 (2026-07-08/09)](stream-scan-discover-4wide-2026-07-08.md) — 定时链路改流式管道拿实时数据+有推荐就立马下单(消费线程); 智谱无1302硬墙/按账户限流/重调用~4并发甜区
- [全自动监控页取代半自动界面 (2026-07-09)](dashboard-rework-monitor-2026-07-09.md) — 新首页 auto_dashboard.py(按天战报+实时看板); /panel /api_reeval 删; dashboard.py 零改动(view_functions覆盖); 只留应急停止+单仓清仓
- [单仓金额冻结 (2026-07-11)](kelly-bankroll-freeze-2026-07-11.md) — 加现金每仓不放大(冻结Kelly参考本金=AUTO_KELLY_BANKROLL_REF=50), 现金拿去多开仓; 否掉硬封顶; 全在auto_trader.py
- [止损/重评大改 (2026-07-18)](stoploss-reeval-redesign-2026-07-18.md) — 收敛&混合砸穿直接平仓; 事件-50%硬止损+盘中"最好点回撤5pp"触发重评(无冷却); exit护栏删/cancel_autostop删; 每日15:00全仓重评照旧; 改monitor.py+auto_reeval.py
- [铁律: 文档跟代码同步 (2026-07-18)](feedback-docs-sync-with-code.md) — 改代码=顺手改版本号+技术报告(含正文)+CLAUDE.md, 不用单独问; 用户确认改程序已含文档同步
- [运行诊断报告生成器 (2026-07-20)](run-diagnostic-report-generator.md) — 那份PDF体检报告怎么出/更新: scripts/gen_run_report.py 读实时holdings API+v4.db → report.html → 无头Chrome打印PDF; poppler渲染做QA; 含止损档列
- [三号账户 shadow (2026-07-24)](shadow-third-account-2026-07-24.md) — auto_shadow.py: 测试仓那半(≤0.40)真买$2/仓, 止损-60%+$0.05地板不止盈拿到结算; 止损值来自18条低价仓回撤研究(唯一赢家最深跌55%); 隔离照抄bench; 现DRY空跑等用户凭据
- [Bench 第二账户基准策略 (2026-07-23)](bench-second-account-2026-07-23.md) — 纯测AI准确率: $2/仓·-30%即卖·无重评·持到结算·双台账(止损不污染准确率); 现DRY_RUN等凭据; 双账户隔离铁则
- [卖不掉的仓无限重试 (2026-08-27)](stuck-unsellable-positions-2026-08-27.md) — 无订单簿的仓每30s重试卖出永不停; bench 有退避+尘埃仓强关, monitor.py 按铁律不能改; 要修得开独立新文件且先问用户
- [三账户对照报告 (2026-08-27)](three-account-report-2026-08-27.md) — scripts/gen_3acct_report.py 出 PDF; 口径铁律「以资产真相为准, 台账漏废仓/vanished 会高估」; 7-8月结论: 赚钱的是止盈止损不是选品, GLM ≤$0.30 区间 12投0中
- [智谱搜索API不认count了 (2026-09-01)](zhipu-search-count-ignored-2026-09-01.md) — 恒返50条→context翻倍→选品撞20min熔断+账单翻倍; 变化发生在08-12~08-27停机窗口, 我方代码没动; 修法=自己切items
- [项目付费API已停 (2026-09-01)](project-api-stopped-2026-09-01.md) — 用户令: 关GLM选品+重评, 仓位/盯盘/bench/shadow继续; 两个可逆开关+恢复三步; 顺带修了「API紧急暂停」挡不住每日巡检的bug
