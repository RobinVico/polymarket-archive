<div align="right"><a href="README.md">English</a> | <b>中文</b></div>

# Polymarket 全自动交易系统 (AUTO v8.5.5)

> 一套零人工的 Polymarket 预测市场全自动交易系统：定时扫描 → LLM 选品 → 写死规则分流 → 自动下单 → 盯盘 → 自动重评 → 自动出场。同一批 AI 推荐喂**三个真钱账户**跑三种出场策略。这是本项目的**最新版本**，代码在 [`latest_AUTO-v8.5.5_three-account-system/`](latest_AUTO-v8.5.5_three-account-system/)。

## 它是怎么运行的

**一条全自动流水线**（一个进程，端口 5052）：

```
定时扫描 ──→ GLM 选品 ──→ 写死规则分流 ──→ 自动下单 ──→ 盯盘 ──→ 自动重评 ──→ 自动出场
09:00/21:00   联网深度调研    0.40<价<0.85     Kelly仓位     每30秒     大跌触发+每日     止盈/止损
27个白名单tag  输出JSON推荐    真买,否则测试仓   +信心乘数                15:00全仓巡检     /重评说卖
```

1. **扫描**：每天 09:00 / 21:00 扫 27 个白名单 tag（`modules/tags.py`），机械过滤流动性/价格/日期，产出候选报告；
2. **选品**：候选 ≥5 个的 tag 送智谱 GLM（多轮自主联网搜索 agent），回结构化 JSON 推荐（方向 + 胜率估计 q + 信心）；
3. **分流**：写死规则——新鲜盘口价在 **0.40~0.85** 之间才真钱买入，其余进免费测试仓；关键词黑名单强制只进测试仓、绝不真买；
4. **下单**：1/4 Kelly 公式定仓位（本金参考冻结 $50，信心乘数 ×0.75~1.25，单仓硬顶 $5），临下单复核盘口，漂移 >3pp 就放弃；
5. **盯盘**（纯价格逻辑，零 API 成本）：三档止损——收敛型峰值回撤 20%、混合型 35%、事件型 −50% 硬止损，连拍确认后直接平仓；止盈翻倍全卖 / 0.92 卖半等梯队；
6. **重评**：事件型仓位从持有期最好点回撤 ≥5pp 触发一次 GLM 重评 + 每天 15:00 全仓巡检；重评判 exit 立刻卖出，配方向纠错反问闸防 AI 把胜率数字填反。

**同一批 AI 推荐喂三个真钱账户**，对照三种出场哲学：

| 账户 | 出场规则 | 入口 |
|---|---|---|
| 主账户 | 上面的完整策略 | `modules/auto_trader.py` + `modules/monitor.py` |
| Bench 基准 | 照单全收，仅「亏 30% 即卖」，其余持有到结算 | `modules/auto_bench.py` |
| Shadow 低价 | 只买 ≤0.40 的推荐，−60% 止损，不止盈持有到结算 | `modules/auto_shadow.py` |

三个账户各有独立监控页（`/`、`/bench`、`/shadow`），资产曲线、按天战报、事件流全程留痕。

## 怎么跑起来

```bash
cd latest_AUTO-v8.5.5_three-account-system
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # 填入你自己的钱包/API 凭据 (本仓库不含任何密钥)
bash restart.sh             # 入口 autobot.py, 面板 http://localhost:5052
```

注意：Polymarket 2026 新架构存款钱包必须 `POLY_SIGNATURE_TYPE=3`；`py_clob_client_v2`（1.0.2）已 vendor 在目录里，勿降级。封存时智谱选品/重评 key 处于停用状态（上游搜索 API 变更导致成本失控），恢复方法见目录内 `CLAUDE.md`。

## 想回顾以前的版本和历史迭代？

全部在 [`history/`](history/)：**从 [项目总结报告（双语 HTML，默认英文可切中文）](history/00_final-reports/Project-Summary-Report_2026-09-20_bilingual.html) 或 [中文 PDF](history/00_final-reports/Polymarket项目总结报告_2026-09-20.pdf) 看起**（完整时间线、三账户最终战绩、事故簿、经验教训），然后按编号顺着走——`01` 史前浏览器自动化原型（2026-04）→ `02` v3 半自动初版 → `03` 半自动主项目 v4~v7（更早的 v4/v5 逐代归档嵌在其 `past/` 里）→ `05` 早期文档与研究 PDF → `06` 天气市场支线。双语索引见 [`history/README.md`](history/README.md)。

## 🔒 脱敏与免责

本仓库为封存快照：所有 `.env`/密钥/浏览器登录态/AI 会话记录/运行日志已在上传前移除（仅留 `.env.example` 模板），全部真实密钥值经逐值反查确认零残留。项目已封存、不再维护；预测市场交易有实质亏损风险，本仓库不构成任何投资建议。

*2026-09-20 封存 · RobinVico*
