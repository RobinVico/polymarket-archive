# Polymarket 交易机器人项目档案 (2026-04 → 2026-09)

> Complete archive of a 5.5-month Polymarket trading-bot project: from a browser-automation prototype, through a human-in-the-loop semi-auto system, to a fully autonomous GLM-driven pipeline running a 3-account live-money strategy experiment. **All credentials removed** — see sanitization notes below.

一个跑了五个半月的 Polymarket 预测市场交易机器人项目的**完整封存档案**：从浏览器自动化原型（v1）→ 半自动（人拍板、bot 执行，v3~v7）→ 全自动（扫描→GLM 选品→自动下单→自动重评→自动出场，v8）→ 三个真钱账户的策略对照实验，2026-09-20 封存。

## 📖 先看什么

- **[项目总结报告 (PDF)](00_封存总报告/Polymarket项目总结报告_2026-09-20.pdf)** — 全项目总览：干了什么、逐条迭代时间线、最终战绩、事故簿、重启改进清单（另有 .docx/.html 可编辑版）
- **[三账户终版报告 (PDF)](00_封存总报告/三账户终版报告-2026-09-20.pdf)** — 三种出场策略的真钱对照实验终版数据

## 🏁 最终战绩（资产真相口径 = 现总资产 − 净投入）

| 账户 / 策略 | 净投入 | 封存日资产 | 盈亏 |
|---|---:|---:|---:|
| 主账户 · 全自动完整策略（Kelly 仓位 + 三档止损 + 止盈 + GLM 重评） | $99.66 | $90.61 | **−9.1%** |
| Bench · 基准对照（GLM 推荐照单全收，仅亏 30% 即卖） | $90.47 | $41.81 | **−53.8%** |
| Shadow · 低价拿到底（只买 ≤0.40，−60% 止损，持有到结算） | $50.00 | $22.16 | **−55.7%** |
| **合计** | **$240.13** | **$154.58** | **−35.6%** |

**核心结论**：① 同一批 AI 推荐，出场规则不同结局天差地别——**赚（少亏）的钱来自止盈止损纪律，不是选品**；② GLM 裸预测整体判对率 56.8%（83/146），但低价区（<40¢）只有 11/45——**低价长尾被 LLM 系统性高估**；③ $2~5 的小仓位下交易磨损占比过大，策略再好也难覆盖。

## 📁 目录结构（按时间顺序）

| 目录 | 阶段 | 时间 | 内容 |
|---|---|---|---|
| `00_封存总报告/` | — | 2026-09-20 | 总结报告（PDF/docx/html）+ 三账户终版报告 |
| `01_史前_v1_polymarket-bot_…/` | v1 | 04-08 ~ 04-16 | 最早尝试：浏览器自动化驱动 Gemini Deep Research 选品（含 04-15 备份、debug 截图） |
| `02_v3_半自动初版_…/` | v3 | 04-27（冻结） | 人下单 + Claude 分析 + bot 分层止盈止损的原型 |
| `03_半自动主项目_v4至v7_…/` | v4→v7.5.4 | 05-09 ~ 07-24 | 主战场：决策引擎/重评体系/Dashboard 在此成型；**更早迭代嵌在 `past/`（v4、v5、v5.6~5.9 逐代归档）**；含交易数据库与两份 PPT |
| `04_全自动AUTO_v8_…/` | v8.0→v8.5.5 | 07-06 ~ 09-20 | 全自动流水线 + 三账户实验；含封存日数据库快照、6 份历史 PDF 报告、4 份分享 PPT、完整技术报告与 CLAUDE.md 规则史 |
| `05_散落文件_…/` | 佐证 | 04 ~ 09 | v1/v2/v3 各代技术文档、5 月份 AI 研究分析 PDF、项目记忆库（memory 笔记） |
| `06_支线_天气bot_…/` | 支线 | 07-12 起 | Polymarket 每日最高温市场套利（日落后温度只降不升，买 0.90~0.995 档位），独立钱包独立策略 |

## 🔒 脱敏说明（本仓库如何做的防护）

与本地母档案相比，上传前**移除**了：

1. **全部凭据**：所有 `.env`、`.env.bak_*`、`_local_secrets/`（钱包私钥、交易所凭据、智谱/Anthropic API key、面板密码）——仅保留 `.env.example` 模板；
2. **全部旧 git 历史**（`.git/`）：历史提交中可能存在过的敏感内容一并规避，本仓库为全新单提交快照；
3. **浏览器 profile**（含登录态 cookie）与 **AI 会话原始记录**（可能含贴入过的凭据），仅保留整理过的 memory 笔记；
4. 运行日志（单文件数百 MB 且可能含敏感回显）、`.venv`、`__pycache__`、数据库运行时副本（`-wal/-shm/.bak_*`）。

上传集经过**逐值反查**：从全部 8 个凭据文件提取的每一个真实密钥值，在全部 675 个上传文件（含数据库、PDF、PPT 二进制）中确认零残留。数据库中出现的 `0x…` 地址为链上公开地址与市场 condition id，非私钥。

## ⚠️ Disclaimer

Research-grade software, archived and unmaintained. Trading prediction markets involves substantial risk of loss. Nothing here is financial advice. 本项目已封存、不再维护；预测市场交易有实质亏损风险，本仓库不构成任何投资建议。

*Archived 2026-09-20 · RobinVico*
