---
name: shadow-third-account-2026-07-24
description: "三号账户shadow(auto_shadow.py): 测试仓那半(≤0.40)真买$2/仓, 止损-60%+地板不止盈拿到结算; 现DRY空跑等凭据"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3e9e62ad-6021-4de6-a1eb-e9c1e479904f
---

用户 2026-07-24 拍板: **同一套 GLM 推荐, 三账户跑三策略** — 主策略(全套止盈止损重评) / bench 二号(裸预测基准, 07-23建) / **shadow 三号 = 本条**。`modules/auto_shadow.py` (v8.5.0)。

**策略死规则 (用户 AskUserQuestion 逐项拍板)**: ① 只吃 `status='paper'` 候选 (黑名单强制不吃; ≥0.85 那半永远排除); ② 临下单新鲜 ask **≤0.40** 才买 (用户口头说"45以下", 但确认选了严格测试仓那半 ≤0.40, 避免 0.40~0.45 跟主账户双买); ③ **$2/仓** 固定; ④ **止损不止盈**: 入场锚 **−60%** + $0.05 地板连3拍, 无止盈/无重评/无时间止损, 拿到结算; ⑤ 只买启用后新推荐 (存量 21 个低价测试仓不补买)。

**止损值 −60% 的依据 (07-24 回撤研究, 用户点名要研究的)**: 拉了 18 条低价仓从推荐到结算/现在的真实价格路径 (prices-history API; ⚠️ 裸 python urllib 会 403, 要 curl; DNS 守卫也得装) — 赢家/准赢家4个中途最深跌 6%/14%/31%/**55%**(唯一真赢家胡塞0.38→$1), 输家5个全部奔零 → −50% 会杀掉唯一赢家, −60% 全放过且把死仓从−85%~−100%救回−60%。已结算6条里只赢1条 — 靠没结算的准赢家撑着, 样本极小, 实验本身就是验证这个。

**工程 (照抄 bench 已验证隔离模式, 别自己发明)**: SHADOW_POLY_* env交换构造第二 Executor 实例(主线程 app.run 前) / **绝不用** exe.get_positions(模块级FUNDER=主账户)和 get_cash_balance(写 Executor._live_cash 类缓存会把三号现金漏进主页面) → 自带 _positions(出错返回None不是[])/_cash / 同凭据守卫(连 bench 凭据也查) / pending先落库崩溃不重复买 / 表 shadow_positions/shadow_done/shadow_state / 路由 /api/shadow/status + scan_now。

**现状 (07-24 下午已转真钱, v8.5.2)**: 用户提供第三账户凭据 (funder 0x812D…1Ce0), sig=3 只读验证通, `SHADOW_DRY_RUN=0` 激活, start_at 已重置。**账户余额 $0 待用户充值** — 转真钱时加了"现金不足→候选暂缓不作废" (24h 内每轮重试, 充值到账自动补上车, 无需重启)。另加固: **宇宙闸门复查** (`_in_universe` 真买前自验; 背景: auto_candidates 里发现 id 9000019+ 合成测试行, 不能信任 status='paper' 的来源)。dry E2E 验过: 3 个真实候选全部按规则点名跳过 (两个≥0.85、一个 0.37 临下单漂到 0.41 出线)。**监控页已做 (8.5.3)**: `/shadow` = `modules/auto_shadow_dashboard.py` (主页克隆换数据源, 照 8.5.1 钦定模式逐行抄 bench 克隆模板); 接口 /api/shadow/holdings|history|monitor 形状对齐主页; `shadow_snapshot` 表每10min打点做曲线; 主页+/bench 导航有「🟣 三号低价」入口。充值 $50 已到账 (07-24), 全链体检通过, 等 21:00 扫描出第一批真买。

关联: [[pipeline-steps34-live-2026-07-08]] [[stoploss-reeval-redesign-2026-07-18]]
