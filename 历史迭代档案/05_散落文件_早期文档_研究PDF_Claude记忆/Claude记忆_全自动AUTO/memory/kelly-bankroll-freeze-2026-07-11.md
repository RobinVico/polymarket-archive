---
name: kelly-bankroll-freeze-2026-07-11
description: "单仓金额自定义(auto_trader._suggested_size): Kelly本金冻结不随现金涨 + 置信度乘数high/med/low; sizing.py没动"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3e9e62ad-6021-4de6-a1eb-e9c1e479904f
---

**2026-07-12 追加: 置信度进公式 (用户拍板 "high 下多点 / 中正常 / low 下少点")。** 老 sizing.py 故意不吃 confidence (单层折扣, 只当 metadata); 用户要它进金额 → 在 `_suggested_size` 做成 **Kelly 乘数** `bankroll_usd = kelly_br × conf_mult` (high×1.25 / medium×1.0 / low×0.75, env `AUTO_CONF_MULT_HIGH/MEDIUM/LOW`)。只缩放 Kelly 那步 → high 不破 cluster 上限/$15 顶, low 不破 $1 底; edge 层次 + 信心 两个维度都在。实测 q0.68@0.57: high$4.0/med$3.2/low$2.4。GLM 确实产出 confidence (live high×2/med×42), 认不出→按 medium。sizing.py 仍没动。

---

用户 2026-07-11 拍板: **加现金时, 每仓金额不能被放大 —— 要保持现有 ~$2-3 的下注大小, 加的现金拿去【多开仓】而不是把单仓做大。**

- **明确否掉"硬封顶"方案** (SIZING_MAX_SINGLE_POS=3): 用户原话"很容易全部都变成三" —— 封顶会把所有仓压平到一个数, 丢了 Kelly 的 edge 层次。
- **采纳方案 = 冻结 Kelly 用的"本金"**: `raw = 本金 × kelly_f × ¼` 里的"本金"从【实时总资产】换成【固定参考本金】($50)。公式一个字不改, edge 越大下越多的层次全保留 (低/中/高 edge 仍给 $2.5/$4.5/$7.5 那种区别, 不是全 $3)。
- **cluster 上限 (真实本金×20%) 和月 DD 预算仍按【真实】本金/敞口算** → 现金越多 cluster 房间越大 = 能开更多仓。所以"加钱=多开仓"成立。
- ⚠️ 真正卡"能开多少仓"的总闸是**月 DD 预算 `SIZING_MONTHLY_DD_BUDGET`(默认$30)**: event_driven 档大概十几个仓就到顶, 跟现金无关。想开更多得调高这个 (用户暂未调)。

**实现 (守隔离铁律, 全在 `modules/auto_trader.py`, sizing.py/dashboard.py 一个字没改)**:
- 新 env `AUTO_KELLY_BANKROLL_REF` (默认 0=关=用实时本金=老行为; 现 .env 设 **50**=按$50盘子冻结)。
- auto_trader 不再走内部 HTTP `/api/suggested_size`, 改在本模块 `_suggested_size()` 直接调 `sizing.position_size_usd()` —— 同一个计算器、同样入参, 唯一区别是 `bankroll_usd=` 传冻结值、`cluster_cap_usd=` 传真实值。env=0 时逐字节等价于老 endpoint。
- 老 `/api/suggested_size` endpoint 没动 (半自动计算器已从新 UI 删, 无所谓)。

关联: [[dashboard-rework-monitor-2026-07-11]] [[pipeline-steps34-live-2026-07-08]]
