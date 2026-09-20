---
name: control-panel-spec
description: "副屏'总控台'控制面板 + 紧急红闪弹窗 + 录入漏填提醒 的设计与进度 (用户 2026-06-18 checklist 勾定)"
metadata: 
  node_type: memory
  type: project
  originSessionId: c0f4c148-62b8-42d7-a3a7-e47259a6349f
---

用户要一个放副屏常开的"总控台"控制面板 + 紧急弹窗 + 录入漏填提醒。2026-06-18 用 checklist 勾定。

## B. 控制面板 (新页面 /panel; 跟只读的 /m 分开, 不碰 /m)
- **显示 4 块**(全选): ①顶部大数字(资产/现金/持仓总盈亏/持仓数)+在线状态 ②持仓简表(每仓 名称/盈亏%/状态徽章/距结算/重评灯/🛑止损OFF) ③待处理事项(待重评/手动/已取消止损 + 数量角标, 紧急高亮) ④动态流(谁在涨跌 Top + 最近指令执行/自动卖出日志)
- **操作 3 个**: ①在线/离线切换 ②重评操作直接点(确认/忽略/清空/取消止损/触发) ③一键全部清空。(没选"暂停整个自动API总开关")
- 复用现有 API: /api/snapshot(已含 title/side/avg/cur/pnl/q/days_left/monitor_state) + /api/auto_reeval/pending + /api/presence(+POST/ping) + /api/realtime_movers + /api/logs。控件复用现有 POST 路由。
- 主页加按钮 `window.open('/panel','panel','width=440,height=820')` 开小窗拖副屏; 点开/点关。

## C. 紧急弹窗 (用户原话)
- 控制面板**开着** → 面板内弹普通弹窗 + 红色立马闪烁 + 待处理区也闪。
- 控制面板**没开** → 在主页网页上弹 + 红色闪烁。
- **不要声音。**
- 紧急 = 新的 pending/manual 重评(或离线自动执行了一笔)。检测: 跟踪 seen id, 出现新 id → 弹。

## A. 录入漏填提醒 (独立小保险)
- saveTP(持仓行"保存")时, 止损档 + q + 信心 + cluster 漏任一 → confirm 弹窗提醒(可选仍保存)。防 legacy。

## 进度
- ✅ A 漏填提醒 (saveTP) — 2026-06-18 done
- ✅ C 主页紧急红闪弹窗 (urgent-pop overlay + arLoad 检测新 pending/manual) — 2026-06-18 done
- ✅ **B 副屏控制面板 /panel — 2026-06-18 done**。模块级常量 `PANEL_HTML`(dashboard.py, create_app 前)+ 路由 `/panel`。全 JS 驱动复用 /api/snapshot(补了 autostop_disabled 字段)+ /api/auto_reeval/pending + /api/presence(+ping)+ /api/realtime_movers(items[].change_pp)+ /api/reeval_prompt。主页 nav 加「🖥️ 控制台」按钮 window.open('/panel',460x860)。面板含: 4 块(大数字+在线/持仓简表带灯+🛑OFF/待处理带红闪/谁在动+最近自动动作)、操作(在线切换/确认·忽略·清空·复制提示词/一键清空)、新 pending|manual → 红闪 #pop 弹窗 + 待处理区 .flash。

- ✅ **B+ 卖出事件面板** — 2026-06-18 done (用户迭代过一版)。**口径: 用户说的"系统事件"=卖出事件, 不含 bug/错误** (错误去主页日志区看, 不放面板)。位置: /panel **中列 (原⚠️待处理那列) 砍一半**, 用 `.col2` (flex-column, 两 panel 各 flex:1) 装上下两块: 上=⚠️待处理, 下=💰卖出事件 (`#sells`)。**最初做成顶部 `.sysev` 窄条 + 合并 bot.log 错误, 已废弃** (用户要求砍掉错误源 + 从顶部挪进中列下半)。路由 `GET /api/system_events?limit=N` (默认 12, 只读, 名字保留但只出卖出): 返回 db.events 的 auto_sell/user_sell 倒序, 结构化字段 {kind,label,title,detail,time}; time=`%m-%d %H:%M` (UTC→astimezone 本机, _parse_iso_to_aware)。JS `sells()` 渲染 `.card` 列表并入 8s tick。改这条记 3 处: 路由 + PANEL_HTML 的 `.col2`/`.sell-p` CSS + `sells()` JS。

- ✅ **B++ /panel 布局重排 + 放大** — 2026-06-18 done。`.main` 从 3 列改 **2 列** (`grid-template-columns:1.5fr 1fr`)。**左列** (`.col2`): 📦持仓 (`.col2 .pos-p{flex:1.5}`) 上 + 💰卖出事件 (flex:1) 下 — 两个"长"面板竖叠。**右列** (`.col2`): ⚠️待处理 (`.col2 .todo-p{flex:0 0 auto}` + `.pb max-height:140px`, 常空所以做小) 上 + ⚡谁在动·1h + 📜最近自动动作 (side-p flex:1) 下。字号放大: KPI `.v` 21→28px; 共用的 `.prow`13px/`.nm`13px/`.chg`15px/`.side`10px/`.badge`10px (持仓+谁在动一起变大); 最近动作 card 内联 10→12px (取 8 条); `.subh` 11→13px。谁在动 movers `mov()` slice 3→**5**。布局靠 `.col2` 通用 flex-column + 按 panel 类型 (`.pos-p`/`.todo-p`) 覆盖 flex 实现。

- ✅ **B+++ /panel 字号精调 + 动作详情** — 2026-06-18 done。关键: PANEL_HTML 是独立完整文档, CSS 不污染主页, 所以用 **容器 id scope** 单独调各块大小 (互不影响): 卖出事件 `#sells .card`/`.srow .slab/.stm`/`.sdt`/`#sells .nm` 调大 + `sells()` limit 12→**4** (只显最新几条但更大); 谁在动 `#mv .prow`/`#mv .nm`/`#mv .chg` **调小** (持仓 `#pos` 不受影响, 仍大); 最近自动动作 `#acts .card` **调小** + **点开展开详情** (`.actc`/`.actt`/`.actd`, onclick toggle `.open` 显示 r.reason, 仿主页 1388 行 reason 详情); 待处理 `.todo-p .card`/`.empty` 调大 + `.pb` min-height:48/max:200; KPI `.v` 28→**34px** + `.kpi` padding 加高 (往下拉)。要单独调某块大小就加/改它的 `#id 选择器` scope, 别动共用裸类 (`.prow`/`.nm`/`.card` 改了会牵连多块)。

- ✅ **B++++ /panel 「最新消息」提醒中心** — 2026-06-18 done。待处理 panel **改名 📨 最新消息** (id 仍 todo-panel), 既放原 auto-reeval 待处理项, 又放 4 类**闪烁提醒** (每条红闪 `.msg` + panel `.flash`, 点「确认」`msgAck(uid)` 消除, `seen` Set 防重复弹)。4 类触发**全在前端 poll 里检测, 无后端改动**: ①卖出 (`sells()` 比 /api/system_events 新条) ②持仓波动 ≥**10pp** (`mov()` 比 /api/realtime_movers 的 change_pp, bucket key 防重 + |v|<7 滞回清 seen 允许再报) ③总资产变化 ≥**$3** (`snap()` 比 assets_total, 报后 baseAssets 重置) ④自动重评执行 (`pend()` 的 executed). 首轮静默 (mInit.sells/acts 只记 seen 不弹, 防开页面刷历史); baseAssets 首轮设基线。`renderMsgs()` 统一管 todo-n 角标 / flash / 空态 (= msgs + reevalCount)。同轮还: 谁在动 `#mv`/最近动作 `#acts` 字**调回大** (上轮误调小); 阈值/触发是用 AskUserQuestion 让用户勾的 (全选 4 类 + 10pp + $3)。维护: 检测散在 snap/mov/sells/pend 四个 poll, 全局 msgs/seen/mInit/baseAssets/swingState 在 pAsk 后那段。JS 改完用 `node --check` 验 (py_compile 验不到字符串里的 JS)。

- ✅ **B+5 /panel 加「往期仓位监测」底栏 + 布局** — 2026-06-18 done。`.main` 改 **flex-column**: 上=`.grid2`(原 1.5fr:1fr 两列), 下=新增 **全宽 `.hist-p` 底栏**「🗂 往期仓位监测 · 最近卖出 2 笔」, 里面 `.histwrap`(grid 1fr 1fr)放**最近卖出的 2 笔 closed position 左右并排** `.hcard`。数据**复用 `/api/history/in_progress`**(无新后端路由)取 rows[0..1], `histCard()`/`histRow()` 渲染全字段(方向/成本→卖出/现价/盈亏$%/卖出原因/止损档/tag·簇/持仓时长·次数 + 卖早/卖对 verdict, verdict 算法照搬 renderSellCard in_progress 档: chg=cur-exit, >5 卖早/<-5 卖对)。`hist()` 60s 一刷 + init 调一次。另外: 最近自动动作 **仿主页 auto-reeval 卡** (dashboard.py ~1362-1397 的 arCard/arToggle): **默认折叠**, 一行 = 名称(白 var(--tx)) + `✓已执行`(绿#00e5a0) + 操作 + 红`⚠️论点破`badge + `更多▾`按钮; reason 藏 `.actd`(默认 display:none), 点`更多`走 `actToggle(id)` 展开(原来错做成默认 inline 摘要, 用户要求收起跟网页一样); 谁在动 `.side-p .pb{flex:0 0 auto;max-height:185px}` 收成 5 行紧贴、最近动作 `.pb2` flex:1 吃剩余。控制台窗口 `window.open('/panel'...)` 尺寸 1000x620 → **1240x940**(内容变多, 用户要重开窗口才生效)。维护: 往期卡片字段来自 `_group_closed_rows_into_cards` 的 sells[0] (seq/price/entry_avg/pnl/roi/duration/trigger/change_pp/side/tag/cluster_id/stop_loss_tier)。

- ✅ **B+6 /panel 小恐龙 + 丝滑美化** — 2026-06-18 done。主页那条三只跳恐龙 `.dino-track`(ground+3🌵+🦖🦕🦖)复制到面板顶栏, 放在线/离线 `#pbtn` 之后(flex:1 长条, 时钟 `.lu` 仍靠右)。**关键: 仙人掌动画从 `left` 改 `transform:translateX()` + 容器单位 `cqw`**(`.dino-track{container-type:inline-size}`, `@keyframes cactus-roll{from translateX(101cqw) to translateX(-24px)}`)→ GPU 合成不卡(主页那版用 left 会 reflow 卡); 恐龙跳保持 transform translateY。时钟 `clk()` 拆出来 **1s 一跳**(原来塞在 8s tick 里, 秒数一卡一卡跳 8 秒); body 加 `-webkit-font-smoothing:antialiased` 字更顺; KPI .v 加 color transition。要再加面板动画照这个: 只动 transform/opacity, 别动 left/top/width。

- ✅ **B+7 /panel 真·Chrome 小恐龙游戏(点开可玩)** — 2026-06-18 done。顶栏 emoji 三恐龙仍是**默认装饰**(不变); `🦖 来一局` 按钮(`.dino-btn`)在**顶栏 dino-track 装饰条之后、时钟 `#lu` 之前**(用户要求放这, 不放往期监测里)→ `dinoOpen()` 弹全屏 modal(`#dino-modal`)里 `<iframe id="dino-frame">` 懒加载 `src=/dino/`(没点不加载, 符合"不点就只是装饰")。**游戏=真·Chromium 抽取版 wayou/t-rex-runner (BSD-3), vendored 在 `data/dino/`**(index.html + scripts/runner.js 69KB + img/*.png ×14, 音频是内联 data-URI, 全自包含无外链; 160K; **未 gitignore 会备份**)。两条路由 `dino_index`(`/dino/`→index.html)+`dino_asset`(`/dino/<path>`→asset), 因为 index.html 里 img/scripts 是**相对路径所以必须挂 /dino/ 带斜杠**; flask import 加 `send_from_directory`; `_dino_dir` 从 __file__ 推 repo 根。键盘 space/↑↓ 靠 iframe focus 圈在游戏里不抢面板; Esc/✕ 关闭。改/换游戏只动 data/dino/ + 这两路由, 不碰 PANEL 主体。来源调研: wayou 是 canonical 版(原版单 sprite-sheet, 这个 fork 用拆分 img); 纯 canvas 无 sprite 的 clone(CloudCannon 等)更小但是仿的不是原汁原味。

全部完成。整个 auto-reeval + 控制台 体系到此 feature-complete (除离线自动卖出路径仍未实测; 最新消息提醒中心 + 往期监测底栏 未在真实事件/浏览器实测, 仅 JS 语法+结构+数据接口验证)。
