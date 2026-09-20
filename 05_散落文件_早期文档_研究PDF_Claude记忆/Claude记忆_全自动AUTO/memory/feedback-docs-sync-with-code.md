---
name: feedback-docs-sync-with-code
description: "铁律: 改代码=顺手改版本号+技术报告+CLAUDE.md, 不用单独问; 用户确认改程序=已含文档同步"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3e9e62ad-6021-4de6-a1eb-e9c1e479904f
---

用户 2026-07-18 拍板(有点不耐烦地强调): **只要改了程序(且用户已确认改), 版本号 + 技术报告 + CLAUDE.md 就【必须】跟着改到与代码一致 —— 这是内含的, 不要再单独问"要不要更新技术报告/版本号"。**

**Why**: 用户确认的是"改这个程序", 文档与代码保持一致是天经地义的一部分, 不是另一个要审批的动作。单独问 = 多余、烦人。

**How to apply**: 每次做完一个用户批准的代码改动, **同一轮**里顺手把这些改到一致, 不用再征求同意:
- `modules/version.py` 按规则 bump(patch=小改/minor=大功能, 见 version.py 抬头 + CLAUDE.md「版本号规则」);patch 自行决定, minor 告知用户即可。
- `技术报告.md`: 顶部加/改 **变更日志 blockquote**(跟 8.0.x 同格式)**并且**把相关**正文章节**(如 §4.3 止损 / §五 重评)也改成新行为 —— 不只是加日志。
- `CLAUDE.md`(活文档): 「流水线规则」/「AUTO 分叉补丁清单」/「沿用的关键设计」等相关处同步。
- 只在"要不要额外做别的"或规则本身不清楚时才问;文档同步本身不问。

关联: [[stoploss-reeval-redesign-2026-07-18]]
