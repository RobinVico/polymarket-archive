---
name: bench-second-account-2026-07-23
description: "Bench 第二账户基准策略 (8.4.0) — 纯测 AI 准确率, $2/仓·-30%即卖·无重评·持有到结算; 现 DRY_RUN 等用户凭据"
metadata: 
  node_type: memory
  type: project
  originSessionId: f6ca5027-e95b-488a-be70-b0c58e601e7c
---

用户 2026-07-23 拍板上线 **Bench 第二账户基准策略** (`modules/auto_bench.py`, v8.4.0): 同一份 auto_candidates 推荐照单全收, $2/仓固定, 唯一卖出 = 亏30%瞬时清仓, 无重评/无止盈, 持有到结算。目的 = 拿掉主策略"提前卖出"变量, 测 GLM 裸预测准确率 (背景: 结算层方向对 75% vs 落袋 47%)。

**Why:** 主策略的重评/止损把"AI 方向对不对"和"钱赚没赚"搅在一起; bench 是干净对照组, 双台账设计 (止损卖掉的预测**照样等结算判对错**) 让止损保护本金但不污染准确率。

**How to apply:**
- 用户拍板细则: 黑名单推荐**完全忽略** (不买不打分, 原话"直接不卖"); 反方向不对锁只记 score_only 行照打分; 止损瞬时单拍触发 (拒了连拍确认)。
- **2026-07-24 已转真钱 (8.4.1)**: 第二账户 = **老半自动账户** (funder …E07E, **sig=1** 老架构, 接入时 $90.47 全现金) — 隔离铁律获用户拍板唯一例外, 凭据在本目录 .env `BENCH_POLY_*`。老 bot (5051 main.py) 用户拍板已杀; **老 bot 永远别再启动** (它的 monitor 会按老策略卖 bench 的仓, 基准就废了); cron 只有备份不会重启它。
- **`/bench` 独立监控页** (`modules/auto_bench_dashboard.py`, 设计同全自动主页): 磁贴/资产曲线 (`bench_snapshot` 表, bench 线程每 10min 打点)/准确率桶/持仓/双台账/事件流; auto_bench.py 只留 /api/bench/*。
- 双账户隔离铁则 (改代码必守): bench 绝不碰 `Executor.get()` 单例 / 绝不用 `exe.get_positions()` (模块级 FUNDER 全局=主账户) / 绝不调 `get_cash_balance()` (写 `_live_cash` 类属性会把 bench 现金漏进主页面) — bench 自带 `_positions()/_cash()`。同凭据误配守卫会拒启。
- 幂等: bench_positions `UNIQUE(cand_id)` + pending 先落库再动钱 = 崩溃只丢买入绝不重复买; 游标 `auto_bench_last_cand_id` (app_state) 首启=MAX(id) 不回补历史。
- 页面 `/bench`; 手动触发 POST `/api/bench/consume_now` `/api/bench/score_now`。
- 有一条 dry E2E 活标本 (克隆的 us-x-iran ceasefire NO 候选 id=9000009, status='bench-e2e-test') 会随真实结算被打分 — 验证 scorer 用。
- 关联 [[pipeline-steps34-live-2026-07-08]]
