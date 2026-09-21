---
name: auto-reeval-pending-changes
description: "auto-reeval 自动触发规则的'待改清单' — 用户要逐条审完再统一改; 每次开工/相关时提醒 ta 这个清单还没落地"
metadata: 
  node_type: memory
  type: project
  originSessionId: c0f4c148-62b8-42d7-a3a7-e47259a6349f
---

## ✅ 状态: 2026-06-18 全部实现并验证

> **版本: 这套官方定为 v6.0** (2026-06-18). 之前文里写的 v5.13/v5.14/v5.15 是开发期内部小号, 已统一归 v6.0. **v6.0 分两块: 6.1 = 大跌自动重评 (整个 Claude API 连接, §二十五) / 6.2 = 副屏控制台 + 杂项 (漏填/弹窗/距结算, §二十六)**. 全部文档(技术报告中英 / CLAUDE.md / README×2 / SECURITY×2)已更新. 注意报告里另有个老 §六 也用 6.1-6.4 子号 (不同章节, 别混). 见 [[control-panel-spec]].
清单两条 + 在线/离线模型已全部落地。**当前实际行为**:
- **分档触发**(自动 API): convergent -15% / hybrid -30% / event_driven -30% / legacy -20%。 **⚠️ 2026-07-08 (v7.4.5) 大改: 混合型(含未分类=默认hybrid)不再走重评 —— 砸穿止损线【直接平仓】; 只 event_driven + convergent 砸穿才进 PENDING_REEVAL 交 API 重评。落地: `_maybe_trigger_auto_reeval` 顶部 `if tier=="hybrid": return`; `_evaluate_position` (b) 段 `_direct_stop=(tier=="hybrid")` 跳过 PENDING_REEVAL 走硬卖。止损值也已变(7.4.3~7.4.4): 收敛=回撤20%(≤3天12%)/混合=回撤35%移动止损/事件=入场-60%+$0.05地板。依据=历史数据(20次重评19次hold, 混合型3/4扛到-52%最差; 收敛型有-64%→+92%救援故保留)。**
- **决策 4 项**: hold / update_q / exit / **cancel_autostop**(取消该仓自动止损)。
- **在线** = 暂停自动 API → 手动复制提示词卡片(省钱); **离线** = 自动 API + **自动执行决策(动真钱: exit 自动卖 / cancel 自动关止损 / update_q 自动改 q),无需批准**。决策就绪时若用户已回到在线 → 改挂 pending 等批准。
- **cancel_autostop**: `position_meta.autostop_disabled=1`, monitor 跳过 %止损只留 $0.05 地板; 持仓行显示 `🛑止损OFF`。
- **v5.15 (2026-06-18) 大跳防盲卖**: %止损线砸穿(含一拍跳穿的大跌)**不再盲卖** → monitor `_evaluate_position` 返回 `PENDING_REEVAL`(无卖出动作)→ loop 的 else 触发自动重评 → 等结果(离线 `_auto_execute` 自动执行 exit/hold/update_q/cancel; 在线挂 manual 手动)。**只有 $0.05 地板 / 重评未启用(无 key)才硬卖**; event_driven 与 autostop_off 仍只地板。有 active 重评(含 executed 未清空)期间持续 PENDING_REEVAL 不卖, 用户清空才重新武装(清空后若仍砸穿 → 再触发重评, **永不盲卖 convergent/hybrid/legacy**)。UI: 主页徽章「⏸ 等重评·暂不止损」(橙脉冲, 可点手动复评) + 副屏面板「⏸等重评」(橙)。代码: monitor.py STOP_LOSS 块(~155-190)。
- update_q 确认/自动后**即时重算 monitor_state**(原清单 #2)。
- **v5.15 (2026-06-18) 冷却修 bug + 手动 API 重评 + 统一 prompt**:
  - **修 bug**: 点"清空/重新武装"后会下一拍立刻又自动重评 —— 根因 `COOLDOWN_HOURS` 定义了却没接进 monitor(只查 latch)。已接上 `recent_auto_reeval_exists(token, COOLDOWN_HOURS)`, **默认 6h**(env `AUTO_REEVAL_COOLDOWN_H`)。清空后 6h 内不自动再评。
  - **手动「🤖 API重评」按钮**: 主页持仓状态行(`apiReeval()`)+ 副屏面板每行(`.ar-api`/`arApi()`)+ 测试触发器, 都调现成的 `/api/auto_reeval/trigger`(绕过冷却/latch, 跑 API 不分在线离线)。用途=人在外面懒得手动复制粘贴, 一键让 API 跑。
    - **2026-06-18 改 (用户明确要求): 这个按钮永远 `run_and_store(force_manual=True)` → 结果一律挂 pending 等用户点「✅ 确认执行」, 不管在不在线都不自动执行 (绝不自动动钱)。** 实现: `auto_reeval.run_and_store` 加 `force_manual` 参数; route(dashboard.py ~3146)传 `kwargs={"force_manual": True}`; `force_manual` 时跳过 `_auto_execute` 只 log。**monitor 自动触发(monitor.py ~393)不传 → 默认 False → 保留"离线自动执行"原样** (这是"其他的该自动保留原样"的边界)。pending 卡片复用现成确认 UI(红灯+「✅确认执行」/「✗忽略」)。
  - **API prompt 统一**: `auto_reeval._build_prompt` 改成用 `prompts.build_reeval_prompt`(= 手动复制给 Claude 那份, 含 Gamma 拉的 resolution 规则)+ 附加 `APPEND_DECISION_INSTRUCTION`(联网 + 必须调 submit_decision)。失败退回内置 `PROMPT_TMPL`。
- **v6.0.1 (2026-06-18) bug 审 + 修** (两 agent 审计; 改 monitor/auto_reeval/db):
  - **#1** 闩锁改用 `has_inflight_auto_reeval`(原 `has_active`)→ AI 说 hold/update_q 后不再永久关该仓 %止损; 仍在水下则**每 6h 冷却到点自动再评一次**(默认=时间触发; 用户可换"再跌一档才触发"/硬止损 b/保持现状 c)。
  - **#2** `db.expire_stale_auto_reeval(30)` monitor 每轮跑 → analyzing 卡死(进程重启/死线程)>30min 自动置 error, 不再永久闩。
  - **#3** `monitor._adopt_manual_reevals_if_offline` 每轮: 离线时把遗留 manual 卡接管成自动跑(offline=auto), 防"在线挂 manual→转离线"卡死。
  - **#4** `_auto_execute` exit 卖失败/部分成交(executor<95%返False)→ 改挂 pending(进紧急弹窗)等确认重试, 不再静默 error 搁置剩余仓。
  - **#7** update_q 的 new_q 夹 [0.01,0.99] 防越界污染 edge。
  - 附带修 **datetime 崩**(naive end_date 当 UTC): dashboard 3 处 days_left + `auto_reeval._days_left` —— 之前 reeval_prompt 路由 500 / 复制 prompt 失败。
  - 心跳 `CHECK_INTERVAL` 用户已改 30s(原 180s), 顺带缩小大跳盲区。
- ⚠️ **仍未实测**: 离线自动卖出(`auto_reeval._auto_execute` 的 exit 分支)真触发路径; #4 让部分成交不再搁置但整条 exit 仍没真跑过 —— 动真钱, 留意。
- **✅ #1 已定 (2026-06-18; v6.0.4 改写 2026-06-19)**: 同一仓再评节流 = **过6h 冷却 → 那拍把当前亏损记成基线(`position_meta.reeval_watch_loss`)→ 之后从基线再多亏 ≥10pp(`auto_reeval.RETRIGGER_DROP_PCT`, env `AUTO_REEVAL_RETRIGGER_DROP`)才触发**。取代旧的"过6h 且 已多亏5pp 就立刻触发"(时间一到就放炮)。冷却中清基线; 真触发清基线+重置冷却。闩锁用 `has_inflight`(非 has_active)。首次仍按 tier 阈值。代码: `monitor._maybe_trigger_auto_reeval` + `db.set/get_reeval_watch_loss`。
- **✅ #5 已定**: presence 默认保持 **offline = 自动**(用户确认 OK, 不改)。
- **✅ #6 已加 (2026-06-18)**: 确认按钮并发去重 —— `db.claim_auto_reeval(sug_id)` 原子 compare-and-set (pending→executing); dashboard `auto_reeval_confirm` + `auto_reeval._auto_execute` 都先抢占, 抢不到就跳过 → 杜绝主页/面板双击下两笔卖单。卖失败/异常 → 退回 pending 可重试; `expire_stale_auto_reeval` 回收死在 executing 的行 (>10min→pending)。原子性已测 (第一抢占 True / 第二 False)。
- **审计结论**: #1✅ #2✅ #3✅ #4✅ #5✅(保持) #6✅ #7✅ + datetime 崩✅ 全处理完。唯一剩: 离线自动卖出真触发路径仍没真跑过 (代码+部分成交+并发都加固了, 但首次真卖才算实测)。
- **v6.0.3 (2026-06-19) API 紧急暂停开关**: `app_state.api_paused` + `db.get/set_api_paused`。`auto_reeval.is_enabled()` = `is_configured()` 且 `not get_api_paused()` → 暂停时 auto触发 / 手动🤖 / 离线执行 / adopt 全停。**关键不变量: monitor STOP_LOSS 块用 `auto_reeval.is_configured()`(忽略暂停)而不是 is_enabled()** → 暂停期间砸穿止损线仍冻结 PENDING_REEVAL **不盲卖**(只 $0.05 地板), 避免一按急停批量砸盘。主页 nav `#apimode-btn` + 控制台顶栏 `#p-api-btn`「🤖 API」(暂停变红「🛑 API已暂停」), 共用开关 8s 轮询同步; `/api/api_paused` GET/POST。已功能测试。
- **✅ v6.0.5 (2026-06-19) 在线 manual 卡闪烁超时自动调 API** (用户明确要求): 在线时砸穿触发点(差5pp, 如 -15%/-30%)**不盲卖** → PENDING_REEVAL + 存 manual 卡红闪等手动确认; 但卡闪烁 > `auto_reeval.MANUAL_ESCALATE_MIN` 分(默认2, env `AUTO_REEVAL_MANUAL_ESCALATE_MIN`)还没人理 → monitor 心跳自动升级成调 API。⚠️ **在线升级出来的结果仍只挂 pending 等确认卖, 绝不在线自动卖**(run_and_store 在线分支留 pending, 不进 `_auto_execute` —— 用户原话"他不能直接卖了, 如果在线的话")。落地: `monitor.PositionMonitor._escalate_stale_manual_reevals`(由 `_adopt_manual_reevals_if_offline` 改名扩容): 离线→立即接管所有 manual(动真钱); 在线→只接管 `created_at` 距今 ≥ `MANUAL_ESCALATE_MIN×60s` 的卡(用 `db._parse_iso_to_aware` 算龄)。每心跳(≤30s)跑一次 → "2分钟"实际 2~2.5min 桶。**不变量: 别让在线路径走 `_auto_execute`; 别把"离线立即接管"和"在线超时升级"合并**。已 import/重启验证(无 manual 卡时静默)。 **⚠️ 2026-06-25 用户拍板关掉这条「在线超时升级」**(嫌 2 分钟太短、手动评还没弄完就抢着白花 API 钱): `monitor._escalate_stale_manual_reevals` 的 `if online:` 分支改成直接 `return` —— **在线永不自动补 API, manual 卡留着等手动确认**。离线接管/自动执行**不变**。要恢复就把那个 `return` 换回原来的 MANUAL_ESCALATE_MIN 超时逻辑。
- **✅ v6.0.6 (2026-06-19) 重评历史归档 + 冷却倒计时** (用户要求: 清空别全没了, 要历史+倒计时): 「清空」一直是 `status='cleared'` **从不删数据** —— 之前清掉就看不见了。现在: ① 主页自动重评建议卡下方折叠栏「📜 重评历史 & 冷却状态」(`<details>` 默认收起): `db.get_auto_reeval_history(60)` 列所有已清空记录 + 决策(清仓/q X→Y/取消止损/持有)+ 触发/决策/清空三时间 + 「更多」展开 reason/信心/论点破/来源(跟在线卡同套)。② **冷却倒计时**: `/api/auto_reeval/history` 用 `db.auto_reeval_latest_per_token()` 找每 token 最新记录(只它显示冷却, 老的标 superseded), 对照持仓 + `COOLDOWN_HOURS` 算 cooling(❄️还剩2h13m, `cd_end_ms` 前端每秒 tick)/armed(过6h, 显示 `reeval_watch_loss` 基线 + 再跌10pp)/inflight/closed。前端 `arhLoad()` 每30s 拉 + `cdTick()` 本地每秒走字。③ **面板**持仓行加「❄️Xh」徽章(`pCdBadge`+`pCool` 每30s)。代码: db.py(get_auto_reeval_history/auto_reeval_latest_per_token)+ dashboard.py(/api/auto_reeval/history 路由 + arhLoad/cdTick/arhCdBadge + 面板 pCool/pCdBadge)。已重启验证(7条历史, JD Vance 仓 cooling 还剩49min, 另一仓 armed)。
- **✅ v6.0.7 (2026-06-19) 自动重评多模型: 智谱 GLM 默认 + Claude 兜底** (用户要求: "质朴(=智谱GLM)默认, 调取失败改用 Claude"): 默认先用智谱 GLM (便宜), GLM 失败/给不出合法决策 → 自动降级 Claude Opus (两级)。编排 `auto_reeval.run_auto_reeval`: `_provider_order()` (有 key 的才进, 默认 `['glm','claude']`; env `AUTO_REEVAL_PRIMARY=claude` 反过来) 依次试, 第一个出合法决策返回, 带 `_provider`。`_run_claude`=原 Anthropic 那套(别动); `_run_glm`=新 (`zhipuai` SDK 已 `pip install` 进 .venv + 智谱原生 web_search 联网 + 只输出 JSON → `_parse_glm_decision` 严校验: 合法action/new_q容错0-1/update_q必须有new_q)。决策 dict 字段跟 Claude 完全一致 → 下游 `update_auto_reeval_decision`/`_auto_execute` 不用改。⚠️ **关键不变量: GLM 是尽力而为的便宜主用不是直通 —— 任何异常/非法决策都降级 Claude, 绝不让坏决策进 `_auto_execute` 动真钱** (已 mock 测 5 种降级情况全过)。db `auto_reeval_suggestions` 加 `provider` 列 (NULL-tolerant), 主页卡+历史「更多」显示「由 智谱GLM/Claude 决策」。`is_configured()` 放宽成"任一 key 即可"(没配 GLM key = 纯 Claude 老行为不变, 实测当前 .env provider_order=['claude'])。**用户要做的: `.env` 加 `ZHIPUAI_API_KEY=xxx` 再重启就启用 GLM**; 可选 `AUTO_REEVAL_GLM_MODEL`(默认 glm-4.6, 可换 glm-4.7/glm-5.2)/`AUTO_REEVAL_GLM_MAX_TOKENS`/`AUTO_REEVAL_PRIMARY`。⚠️ GLM 路径加 key 前没真跑过 (但失败也只是降级 Claude, 安全)。
- **✅ v6.0.8 (2026-06-19) GLM 参数拉满 + 实测通过** (用户加好 GLM key, 要求"模型用最好的+参数尽量拉高", GLM 便宜): `GLM_MODEL` 默认改 `glm-5.2` (最强, 1M上下文/128K输出); 开 thinking (`thinking={"type":"enabled"}`, glm-5.2 强制思考) + `reasoning_effort=max` (经 extra_body); web_search 用 `search_pro` + `count=20` + `content_size=high`; `max_tokens=32000`; client timeout 600s。`_glm_create` 容错: SDK 不认高级参数 (TypeError) 按序去掉重试。**已对真实仓位 (Russia/Kostyantynivka) 实测**: GLM-5.2 联网查 ISW 地图等, 40s 出 `update_q→0.28` + 完整理由 + 3 真实来源 URL ✅。⚠️ **关键加固: `_parse_glm_decision` 加正则兜底 `_glm_regex_extract`** —— GLM 常在中文自由文本里塞**未转义的英文引号 `"`** 把严格 json.loads 撑崩 (实测第一次就崩); 现在先 json.loads, 崩了按已知 schema 正则抠 (action/new_q/confidence/thesis_broken 一定拿得到, reason/headline 尽力, sources 用 URL 正则)。**别删这个兜底**。env 新增: `AUTO_REEVAL_GLM_REASONING`(max)/`GLM_SEARCH_COUNT`(20)/`GLM_SEARCH_ENGINE`(search_pro)/`GLM_TEMP`(0.6)。当前 .env 已有 GLM key → provider_order=['glm','claude'], GLM 真在主用了。
- **✅ v7.x (2026-06-22) 主用翻转 Claude + 双模型对比页** (用户要求: "主用换 Claude, 备用质朴; 每仓两个一起跑, 以 Claude 输出为准; 新建一页对比, 智谱别处不显示"): 
  - **`PRIMARY` 默认 `glm`→`claude`** (`auto_reeval.py`): Claude 现在是**权威** —— 驱动主页/面板显示 + **离线自动执行 (动真钱)**。GLM 降为备用。
  - **`DUAL_COMPARE`** (env `AUTO_REEVAL_DUAL`, 默认开): 每次重评两个模型**并行**都跑。新编排 `run_reeval_dual` + `_run_one` (旧 `run_auto_reeval` 变薄包装只取权威)。返回 `{authoritative, by_provider:{claude,glm}}`。权威 = `_provider_order()` 第一个成功的 (Claude → 挂了降级 GLM)。`=0` 退回省钱串行。
  - **用户明确决定 (AskUserQuestion)**: Claude 挂了 + 离线时, **GLM 决策可自动顶上动真钱** (= "备用是质朴")。所以 `_auto_execute` 用权威 d, 不特殊处理 —— 天然吻合。
  - **GLM 严格隔离到对比页**: 新页 `/api_reeval` (`API_REEVAL_HTML` 常量 + 路由) + 数据接口 `/api/auto_reeval/compare` (`db.get_auto_reeval_compare`) + nav「🔬 API重评」。**主列=权威(Claude) 照旧驱动一切**; GLM 完整输出存新列 `compare_json` (DB 迁移, NULL-tolerant), **只**这一个接口吐它。**`/api/auto_reeval/pending` 显式 `r.pop("compare_json")`** → GLM 绝不进主页/面板/重评建议区。`get_auto_reeval_compare` 过滤 `compare_json IS NOT NULL` (只显真双跑记录, 老记录不混入)。
  - **代码**: `run_and_store` 调 `run_reeval_dual` → 权威进主列 (`update_auto_reeval_decision` 加 `compare_json` 列) + `by_provider` 打包进 `d["_compare_json"]`。
  - **💰 成本变化 (重要)**: 之前 GLM 主用 (便宜)、Claude 仅兜底 (rare); **现在 Claude 每次重评都跑 (贵, Opus 联网) + GLM 每次都跑 (便宜对比)**。auto-reeval 只大跌触发 + 6h 冷却, 有界。省钱开关: `AUTO_REEVAL_DUAL=0` (单跑) / `AUTO_REEVAL_PRIMARY=glm` (翻回 GLM 主用), 都不改代码。
  - **验证**: compile/import/4 个 mock 编排测试 (双跑→权威Claude / Claude挂→权威GLM / 双挂→报错不乱卖 / 异常被兜) 全过 + 端点 200 + pending 不泄漏 GLM + 迁移列在。⚠️ **真双跑 (花真钱) 没跑过** —— 下次大跌触发 / 主页点🤖API重评 才会出第一条对比 (页面在那之前显示友好空态)。
- **待定**: legacy 触发阈值暂用 -20%(用户只明确了 20%/35%/事件30%)。

(以下为原始设计与历史记录, 均已实现。)

---

用户在设计 auto-reeval(大跌→自动联网复评→挂 dashboard 等确认)的**自动触发规则**, 决定 **先列清单、暂不改代码**, 一条条审完再统一改。**改之前要提醒 ta。**

当前自动触发逻辑(已在 `monitor.py:_maybe_trigger_auto_reeval`): 只有"对成本亏 ≥ `LOSS_THRESHOLD`(30%)"一条, 且**对所有 tier 都生效** —— 这点要改。

## 待改清单(逐条改, 改前提醒用户)

### 1. [未改, 大改] 分档自动触发 + AI 可"取消该仓自动止损"(2026-06-18 重设计, 取代原"仅 event_driven 30%")
不再是"只有 event_driven 在 -30% 触发", 而是**每档都在各自止损线前 5pp 触发 reeval**, 让 AI(+用户确认)在自动卖出前有机会介入。`freeze_until/freeze_stop_price` 是 v5.6 已删的死机制, **不要复用**。

**1a. 分档触发阈值**(`monitor.py:_maybe_trigger_auto_reeval`, 闩锁照旧):
| tier | 自动止损 | reeval 触发于 |
|---|---|---|
| convergent | -20% | -15% |
| hybrid | -35% | -30% |
| legacy/未分类 | -25% | -20% |
| event_driven | 无(只 $0.05 地板) | -30% 固定(安全网) |
- **5pp 提前只对 convergent(-15%) / hybrid(-30%)**(= `STOP_LOSS_PCT_BY_TIER[tier] - 0.05`)。
- **event_driven 固定 -30%, 不减 5pp**(用户 2026-06-18 明确: 5pp 只对 20%/35% 那两个有效, 对事件 30% 无效)。
- legacy/未分类: 用户只提了 20%/35%, 没提 legacy → 默认也别减 5pp, 暂按 -30% 或不触发, 待用户定。

**1b. 决策 3 项→4 项**(`prompts.py`/`auto_reeval.py` 的 prompt + submit_decision 工具):
- `hold`=继续持有什么都不改(止损照旧, 跌到线仍自动卖); `update_q`=更新 q; `exit`=立即/提前止损;
- **`cancel_autostop`(新)=取消这个仓的自动止损**, 容忍继续亏(变类 event_driven)。提示词说明这 4 项 + 何时该 cancel(论点没破、只是回撤)。

**1c. 落地 cancel_autostop**: `position_meta` 加新列 `autostop_disabled`(别复用 freeze_*); dashboard `auto_reeval_confirm` 收到 cancel_autostop → 置 1; monitor STOP_LOSS 块(153-176)看到 `autostop_disabled` → 跳过 %止损(只留 $0.05 地板兜底)。

**1d. 时序: pending 期间暂缓 %自动止损**(monitor STOP_LOSS):reeval 异步(0.5-2min)+5pp 窗口, 价可能在确认前跌穿 -20/-35 被卖掉。改: 某仓有活跃 reeval(analyzing/pending)→ 暂缓 %止损给决策窗口。取舍: 一直不处理则该仓可能跌穿线也不卖(灯在闪)。**推荐采用, 待用户最终拍板。**

**1e. 醒目提示"自动止损已取消"**(扩展已完成的行内灯): 该仓 autostop_disabled 后, 持仓行加显眼徽章(🛑 自动止损已取消)+ 不同颜色/常亮灯 + 重评栏明确写出机制被改。

**开放问题(推荐默认, 用户可改)**: ①5pp(用户定)②pending 暂缓止损=是 ③cancel 后留 $0.05 地板=是 ④cancel 永久有效、平仓即清。
**注意**: 这套部分超越了 [[event-driven-exit-keep-status-quo]](那是"默认行为保持现状"); 本设计是"加一条 AI+用户 human-in-loop 的逐仓覆盖路径", 默认行为不变, 不冲突。

### 2. [未改] update_q 确认后立刻重算"决策状态"(别等 monitor 心跳)
- 现象: 确认 update_q → q/edge 立刻变, 但"决策状态"badge 还是旧的, 要等下次心跳(≤180s)。
- 根因: `db.apply_auto_reeval_q` 只写 new_tp 不动 monitor_state; dashboard badge 读存的 monitor_state。
- 改法: `dashboard.py:auto_reeval_confirm` update_q 分支, apply 完新 q 后用 新q+现价+阈值(HOLD_MIN_EDGE_PP/SOFT_NEGATIVE_THRESHOLD_PP, dashboard 已 import)即时算 edge-based state(>2pp→HOLD, ≥-3pp→MARGINAL, else→SOFT_NEGATIVE 因已重评), 调 `update_monitor_state`。不能放 db(循环依赖)。附带: 手动 saveTP 同样滞后, 可一并修。

## 已完成 (2026-06-18, 都在 dashboard.py)
- **#2 ✅ 建议卡片默认折叠**: 默认只显示 名称+操作+状态徽章+按钮; 「更多 ▾」(`arToggle`)展开 `ar-det-<id>` 才显示 reason/thesis/来源/信心/亏%/触发时间。
- **#3 ✅ 持仓行名称后闪烁灯**: `.ar-light` span(每行 `.nm` 里, `data-asset`)+ CSS `@keyframes arblink` + `arLoad` 按 `/api/auto_reeval/pending` 点亮。**红=pending(待决策)**, **黄=analyzing 或已处理待清空**。

（这是 living list, 用户会继续加; 有新条目就在这追加。改前提醒用户。）

## 这轮未采纳、留档备查的触发条件
#2 急跌(24h ≥15pp)、#3 临近结算(≤5天且未明显盈利)、#4 大涨(+60% 止盈复评)、最小仓位价值护栏($10)。用户这轮只要 #1(且限 event_driven), 其余以后想要再开。

相关: 整套 auto-reeval 功能 + 闩锁见代码 `modules/auto_reeval.py`; 设计取舍见 [[event-driven-exit-keep-status-quo]]。
