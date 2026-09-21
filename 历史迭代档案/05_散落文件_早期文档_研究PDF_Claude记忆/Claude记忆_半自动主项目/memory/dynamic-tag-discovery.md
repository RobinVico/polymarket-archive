---
name: dynamic-tag-discovery
description: "动态热门标签发现 (suggest-only board /tags) — 让盯防的 tag 跟着交易量热度走 (俄乌→伊朗→世界杯), 用户 2026-06-22 设计 + 首版上线"
metadata: 
  node_type: memory
  type: project
  originSessionId: f4190ef0-35c0-431a-a3ef-e66390b9db6e
---

用户要 tag 列表跟着世界热点走 (一开始俄乌 → 伊朗 → 世界杯), 别一直扫凉了的、白费 AI 注意力。

## 设计 (用户 2026-06-22 拍板)
- **只建议, 不自动轮换**: 每天产出「今日热门标签」board, 用户一键 纳入/退场/拉黑。
- **固定核心 + 动态热门**: 核心 = 手写 `modules/tags.py` 的 TAGS (永不退场, 留 tier 提示词); 动态 = 用户采纳的, 存 `data/dynamic_tags.json` (跟核心分开)。
- **按交易量门槛 (数量浮动)**: 不固定 top-N, 设金额门槛、数量随之浮动。

## 实现 (首版 ✅)
- `modules/tag_discovery.py` — 引擎 (只读): 拉 Gamma 交易量最高 ~300 active events → 按 tag 汇总 7天成交量 → 排除黑名单+META_TAGS+体育/币价变体(`_BLOCK_KEYWORDS`)+已盯 → 门槛过滤 → 排名。`discover_hot_tags()` / 带 6h 缓存的 `get_suggestions()` / `adopt_tag` `retire_tag` `blacklist_tag`。存档 `data/dynamic_tags.json` (dynamic[] + extra_blacklist[]), 缓存 `data/tag_suggestions.json`。
- `modules/tag_routes.py` — `/tags` 页 (TAGS_HTML) + 路由, 用 `register_tag_routes(app)` 在 dashboard.py `create_app` 末尾一行挂上 (不污染 dashboard.py, 走同一 _require_auth)。页含: 🔥今日热门(门槛滑块前端过滤+纳入/退场/拉黑) · 📌已盯 · 📋白名单(按tier) · 🚫黑名单 · 📅规则说明。
- `modules/scanner.py:_resolve_tag_cfg()` — `scan_by_tag` 改成走它 (先 TAGS 再动态), 所以采纳的 tag 能被单独扫 (lazy import 防 tag_discovery↔scanner circular)。
- nav 加 `🏷️ 标签` 链接 (主页 + 各页 replace_all)。

## 关键坑 / 口径
- **黑名单本就排除 体育/币价/天气** (AI 没 edge), 所以"最热非黑名单"正好= 最热可交易 (世界杯=体育被正确挡掉)。
- Polymarket 有 `2026 FIFA World Cup` 这种年份变体绕过精确黑名单 `FIFA World Cup` → `_BLOCK_KEYWORDS` 关键词兜底。
- 还有大量结构性 meta tag (Hide From New / Tournament Futures / Main Election / Earn 4%) → META_TAGS 过滤。
- 门槛是**前端滑块**: 数据缓存在 $200K 低地板, JS 按用户门槛(默认$10M)过滤显示, 拖动不重打 Gamma。

## 页面排版 (用户 2026-06-22 拍板)
顺序: 📋核心(主) → 🧲动态采纳(副, 带「删除」退场) → 🔥今日热门·当天(不折叠, 带「纳入」/「🚫拉黑」) → 🚫黑名单(不折叠) → 📅规则。核心带 🔥 标当前有量。

## ✅ scan 集成 + /tags 变扫描中心 (2026-06-22 done)
- `scan_by_tag` + `scan_all_tags` 都过 `_resolve_tag_cfg` / merge 动态标签 → **一键全扫会把采纳的动态标签一起扫**。
- **/tags 现在是扫描中心** (用户要求把市场扫描器搬过来, 首页留着没动): 顺序 🔍市场扫描器(一键全扫按钮+状态) → 📋核心(chip 点击复制提示词+扫描状态圆点+🔥) → 🧲动态(复制/删除+状态) → 🔥今日热门(纳入→进动态被扫) → 🚫黑名单 → 📅规则。**全复用现有路由**: POST `/api/scan_all` + `/api/scan_all_status`(manifest, JS 按 tag_label 映射状态) + `/api/full_prompt?tag=X`(复制提示词)。无后端新增、无首页改动。
- 流程: 今日热门「纳入」→ 进动态 → 「一键全扫」(扫核心+动态, 后台1-3min) → 点任意标签「复制」拿 prompt 给 Claude。

## ✅ 首页扫描器整套搬到 /tags (2026-06-22 done)
- 用户要"完美复制首页市场扫描器到 /tags + 删首页 + tier 重排"。**/tags 现在含整套扫描器**(verbatim 搬): tab(Tag扫/关键词扫) + setKw快捷 + doScan + doScanAll一键全扫 + doTagScan单扫 + copyP/copyScan + #scanReport报告 + 状态徽章。加了自带 showT/.toast(首页 showT 是 shared 留着)。CSS 补了 .tag-chip*/.tab/.chip/.pbox + 首页色变量(--ac/--ac2/--vi/--am/--rd/--acd)。
- **tier 重排(显示)**: T1/T2 从 whitelist_by_tier 渲染 chip; **T3=🔥热门=动态采纳(LISTS.dynamic) 渲染成 chip**; T4=原tags.py tier3; T5=原tier4; T4/5 在 `<details>` 折叠。一键全扫 doScanAll 传 `tiers:[1,2]` → scan_all_tags 扫 T1+T2+动态 = 核心+热门; T4/5(tags.py tier3/4) 不在 filter 不扫。**后端没改**, 全对得上。
- 删了 /tags 上单独「固定核心白名单」块(tier chip 就是名单)。动态采纳表保留(扫/复制/删除)。

## ✅ 首页扫描器已删 (2026-06-22 done)
- 从 dashboard.py 首页 HTML 删了整套市场扫描器 **348 行** (5335→4987): #sec-scan HTML 块(370-496) + scanner JS(switchTab~doTagScan 883-1016, setKw/_scanPollTimer/doScan 1018-1033, setScanStatus/pollScan/loadScan/copyScan/loadScan() 1050-1075, copyP 1736-1758) + .tag-chip* CSS(130-150) + 锚点 chip(363)。用带 start+interior 断言的 Python 脚本按行删(高→低), 保住了 trap: **showT(882)/toggleAllEvents(1036-1049)/.btn-primary(151)/.chip/.pbox 没动**。备份 `modules/dashboard.py.bak_pre_scanner_del`。验证: 0 dangling ref, 首页+/tags 都 200, 扫描器在首页消失、事件中心/持仓详情/toggleAllEvents 都在。
- **扫描现在只在 /tags**。首页干净了。

## ⬜ 还没做 (下一步)
- 每天**自动刷新** (现在 6h 按需缓存; 挂 cron 或 monitor 心跳)。
- 退场判定= 这次没达 $200K 地板; 可加"连续冷 N 天"更稳。
