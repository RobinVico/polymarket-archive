---
name: project-api-stopped-2026-09-01
description: 2026-09-01 用户令停掉付费API部分, 仓位/盯盘/bench/shadow 继续跑; 怎么恢复
metadata:
  type: project
---

**2026-09-01 用户原话: "先把这个项目直接停了, 还在跑的仓位让他们继续, 就关闭API的部分其他程序继续"**
(起因见 [[zhipu-search-count-ignored-2026-09-01]])

**关掉的 (两个开关, 都可逆):**
1. `.env` 的 `ZHIPUAI_API_KEY_DISCOVERY` → 改名成 `ZHIPUAI_API_KEY_DISCOVERY_OFF` (key 原样保留)。
   走 `auto_discovery.is_configured()=False` 的既有分支 = **照常免费扫描, 但不调 GLM**。
2. `set_api_paused(True)` (主页「API模式」按钮 / `POST /api/api_paused`) = 关掉**全部重评**。
   一并关掉 Claude 兜底 —— 因为 `is_enabled()` 在选模型之前就拦了。

**仍在跑的 (零 API 花费):** monitor 止盈/止损 (纯价格逻辑) · bench 亏30%止损 · shadow 入场−60%止损 ·
三个监控页 (`/` `/bench` `/shadow`)。**不会有新买入** (没候选了)。

**顺带修的 bug:** 官方「API 紧急暂停」开关**原本挡不住每天 15:00 的全仓巡检重评** ——
`auto_reeval.run_and_store` 入口没查 `api_paused`, 只有 monitor 的盘中触发查了。
已在 `auto_daily_reeval.maybe_run()` 补 `get_api_paused()` 早退。

**恢复三步:** ① `.env` 去掉 `_OFF` ② 主页「API模式」取消暂停 ③ `bash restart.sh`。
⚠️ 恢复前先处理上游那个 count 问题, 否则超时和双倍账单照旧。
