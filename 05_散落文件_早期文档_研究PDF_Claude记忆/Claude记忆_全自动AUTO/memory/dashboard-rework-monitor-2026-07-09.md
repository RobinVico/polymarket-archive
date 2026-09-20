---
name: dashboard-rework-monitor-2026-07-09
description: "全自动监控页取代半自动老界面; 首页=auto_dashboard.py, /panel与/api_reeval已删; dashboard.py零改动"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3e9e62ad-6021-4de6-a1eb-e9c1e479904f
---

2026-07-09 用户拍板重做网页界面 (半自动老 UI 全自动用不上)。新监控页 `modules/auto_dashboard.py` (独立新文件):

- **首页 `/` 现在出监控页** —— 在 autobot.py 用 `app.view_functions["index"]=<monitor_view>` 覆盖 (老 index/半自动代码留着不再被访问); `/monitor` 直达同页; 新接口 `/api/auto/monitor` 只读聚合 (按天战报+警报+选品+候选+重评)。**dashboard.py 一个字没改** (隔离铁律), 以后同步老项目零冲突。
- **删的页 (autobot 里覆盖成跳回 `/`)**: `/panel` 副屏总控台 + `/api_reeval` Claude/GLM对比页 (半自动产物)。
- **留的页**: `/history` `/paper` `/m` (dashboard.py 原样服务)。
- **页面布局 (用户选"两者都要")**: 顶部按天战报 (每天: 下了什么舱/多少钱/卖了啥/警报) + 下面实时看板 (持仓+盈亏 / 资产曲线 / 警报feed / 每日重评巡检 / GLM选品状况 / 未成交候选)。
- **手动开关 (用户选"应急停止+手动清仓")**: 只留两个安全阀 —— 顶部 ⏹应急停止 (`/api/control` stop) + 每仓 🔴清仓 (`/api/force_exit`, 带二次确认)。其余半自动控件 (算金额/粘Claude JSON/填q-tier/在线离线切换/手动重评) 全随老主页下线。
- 警报分级: 🔴无档案仓 / 🟠GLM报错超时·候选被拒(宇宙外/防对锁) / ⚪已持有跳过。数据源全复用现成表 (events/auto_trades/auto_discovery_runs/auto_candidates/auto_reeval_suggestions)。
- ⚠️ **持仓显示铁律 (用户 07-09 第三次反馈: "仓位显示要跟以前一样, 不能改显示内容, 现在显示东西变少了")**: 当前持仓面板必须**逐字段复刻老主页 #pos-panel-current 只看面板** —— 10 列: 名称(+🛑止损OFF)/方向/距结算/入场价/当前价/份数/当前价值/盈亏%/盈亏$/q·信心·止损(彩色 vchip) + 下面决策状态 monitor_state 徽章。⚠️ /api/snapshot **不吐** confidence/stop_loss_tier → 本模块新增 `_build_holdings()` + `/api/auto/holdings` 自己读 position_meta 补全 (顶部四指标也从这个接口出, 不再依赖 /api/snapshot)。**别再把持仓简化成几列小表**。
- 前端**整套设计系统照抄老 dashboard.py**: Space Grotesk + JetBrains Mono 字体(Google Fonts) / 渐变卡片 .card+.chd / 区块标签 .sl / 指标磁贴 .ms.m / **资产曲线用 Chart.js 4.4.1 + date-fns adapter (jsdelivr CDN), 全宽 280px, 跟老页 loadChart 一样(青色资产线+虚线成本线+绿/红渐变填充+悬停tooltip)**。⚠️ 首版我图省事用了系统字体+手绘 canvas 曲线, 用户嫌"太粗糙、太乱、美化全没了" → 07-09 二次照抄老风格重做(内容不变, 只换皮)。CDN 依赖: 断网时字体退化+曲线不画(guard 了), 其余照常。已 restart+HTTP实测全通(浏览器插件没连, 没截图)。
- **待办**: CLAUDE.md「页面」段还写着老 5 页导航, 未更新 (用户没要求; 若要可补一段记这次重做)。

关联: [[pipeline-steps34-live-2026-07-08]] [[stream-scan-discover-4wide-2026-07-08]]
