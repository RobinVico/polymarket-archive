---
name: weather-bot-project
description: "独立天气 bot (~/天气, 端口5053) — Polymarket 每日最高温市场, 日落后吃确定性收益; 专用新钱包(待用户开号), 关键规则和坑都在这"
metadata: 
  node_type: memory
  type: project
  originSessionId: a8b1e174-3e92-41fb-b94a-8d58fb4267f3
---

**天气 bot** (2026-07-12 建): `/Users/baymaxagent/天气`, dashboard http://localhost:5053, 独立 .venv + 独立 git (本地, 无远程)。重启: `bash start.sh` (只杀 5053, 碰不到 5051/5052)。

**策略 (用户定, 激进档)**: 日落即下单; 现温比当日最高低 ≥1°C; 买价 0.90~0.995; $5/市场, 日限 $30; 城市 = 上海/北京/深圳/成都/武汉/香港 (台北有市场但用户没点头, config 里 enabled=False; **澳门没有市场**)。

**关键实证 (别推翻)**:
- 香港结算源 ≠ 机场 METAR! 是 **HKO 天文台总部 Daily Extract, 0.1°C 精度**; 实时数据用 `latest_1min_temperature.csv` (同站同精度)。
- **香港档位取整 = floor** (33.5°→33 档): 2026-07 全月官方 vs 市场赢家 9/9 实证, selftest `t_hk_rule` 每次回测。
- 大陆城市结算 = Wunderground 机场页 = METAR (aviationweather.gov 同一份, 整数°C): ZSPD/ZBAA/ZGSZ/ZUUU/ZHHH。
- 市场 endDate = 当地 20:00 名义截单; 夏天成都日落 (~20:09) 在其后 → 代码有 `PRE_CUTOFF_MIN=10` 提前决策分支。
- **新注册 Polymarket 账户必须 POLY_SIGNATURE_TYPE=3** + vendored py_clob_client_v2 **1.0.2** (抄 polymarket-auto, 1.0.0 sig=3 签名报错)。

**铁闸 (别删)**: "市场共识档 ≠ 我们算的档 → 拒绝下单" 护栏是数据口径错配的最后保险丝; HK 覆盖守卫 (当日首条观测 ≤11 点) 防半路启动漏午间峰值误判档位。

**手续费 (2026-07-12 官方核实)**: 天气类只收 **taker 5%** (公式 `股数×5%×p×(1−p)`, USDC 成交时收; maker 免费; 结算/提现零费) ≈ 吃掉毛利 ~5%, $5@0.97 净赚 $0.147/夜。CLOB `taker_base_fee=1000` 只是签名授权上限; clob 1.0.2 自动按市场费率签单。模拟盈亏已扣费 (`decide.fee_usd`)。⚠️ 天气市场最小 5 股, trader.buy 已防 0.995 价位凑步长凑出 4 股被拒。

**钱包/模式状态**: 用户选了全新钱包但还没开号; **2026-07-12 用户定: 先 PAPER 模拟几天** (.env PAPER=1, 每天日落照常决策记 would_buy + 扣费模拟盈亏), 看完命中率再开真钱 (开号填 .env + PAPER 改 0)。主 bot / auto 完全没动 (新钱包 = 零冲突)。

相关: [[full-auto-account-plan]] (sig=3 经验来源), [[dns-poisoning-polymarket]] (gamma_client DoH guard 已 copy 进天气项目)。
