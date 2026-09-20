---
name: docs-i18n-parity
description: User preference for the polymarket project — any documentation update must be synchronized across both Chinese and English versions; do not leave a version-bump-only English doc when the Chinese doc has new section content
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1666420a-baee-4aee-b81c-9e01ae40f652
---

文档更新中英双版必须同步, 不能只更中文版.

**Why:** 用户 2026-06-01 明确说: "所有的这些中英版肯定要是一样的". 之前在 v5.9 落地时, 我给 `技术报告.md` 加了完整 §十九 (11 个子章节), 但 `TECHNICAL_REPORT.md` (英文版) 只改了 header 版本号 v5.8 → v5.9 没补具体细节内容. 用户察觉后明确指出这种行为不可接受.

**How to apply:** 任何修改 `技术报告.md` (中文) 的 commit, 都必须同时修改 `TECHNICAL_REPORT.md` (英文摘要版) — 不一定逐字翻译, 但必须有对应的英文章节覆盖同样的设计 / 决策 / 代码骨架 / 验证. 同样, 修改 `README.zh.md` 必须同时修改 `README.md`; 修改 `SECURITY.zh.md` 必须同时修改 `SECURITY.md`. 单边更新会被视作 bug.

不仅是顶层文档. 也适用于:
- 任何新 SKILL.md 加中文/英文 examples 时
- CLAUDE.md (这是内部规则, 单文件无需 i18n)

例外: `技术报告.md` 是详尽 17+ 节中文版, `TECHNICAL_REPORT.md` 设计为"英文摘要"风格更短. 不需要逐章节 1:1 翻译, 但**每个新 §N 主章节**(如 §16 v5.7 / §17 路线图 / §18 v5.8 / §19 v5.9) 在英文版**必须有对应小节** (即使精简到 100-200 字).

参见 [[v5-7-hardening]] 和 [[v5-8-concurrent-scan]] 等版本章节, 它们的英文版应该跟中文版同步存在.
