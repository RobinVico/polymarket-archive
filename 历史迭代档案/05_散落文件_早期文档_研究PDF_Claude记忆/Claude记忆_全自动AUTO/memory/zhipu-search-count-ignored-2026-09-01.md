---
name: zhipu-search-count-ignored-2026-09-01
description: 智谱 Web Search API 不认 count 参数了(恒返50条)→ context翻倍 → 选品撞20min熔断; 项目已按用户令停掉付费API
metadata:
  type: project
---

**2026-09-01 诊断结论: 选品老报错不是 bot 的锅, 是智谱改了上游 API。**

- 智谱 `/api/paas/v4/web_search` **无视 `count` 参数**, 不管传 15 还是 50 都返 **50 条 (~95k 字符)**。
  实测两次对比确认。`auto_glm_agent._rest_web_search` 老老实实传了 `count=SEARCH_COUNT(15)`, 没用。
- 后果链: 8 轮搜索 × 50 条 → prompt context 从 **~15万 顶到 30~50万 tokens** → GLM 消化不完 →
  撞 8.3.2 的 `AUTO_DISCOVERY_TAG_TIMEOUT_S=1200` (20min) 硬熔断。近 7 天 **13 次超时** (World 4 次最多),
  且 **每轮 prompt 1.4M→3.0M tokens, 账单翻倍**。
- **变化窗口 = 08-12~08-27 那次停机**: prompt tokens 按天看, 08-12 前平均 13~15万, 08-27 后 25~32万 —— 
  这期间本项目代码一个字没动 (只改了曲线渲染), 所以是上游变的。
- 另有少量智谱**内容过滤**挡 China tag (老毛病, 同 CLAUDE.md 规则16 当初删 Politics 的原因), 量很小。

**如果以后要恢复**: 最干净的修法是在 `_rest_web_search` 里**自己把 `items` 切到 SEARCH_COUNT**
(`items = (data.get("search_result") or [])[:n]`) —— 既然上游不认 count 就我们自己截。
`auto_glm_agent.py` 是 AUTO 自有文件, 改它不违反隔离铁律。用户当时选的是**先整个停掉**而不是修。

**当前状态 (v8.5.5)**: 付费 API 全关, 仓位继续跑 —— 见 [[project-api-stopped-2026-09-01]]。
