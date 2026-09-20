---
name: full-auto-account-plan
description: "全自动新账户项目: 基础已搭好(~/polymarket-auto, 端口5052, 私有repo), 等用户给新账户密钥 + 商讨保护/门槛后开工改造"
metadata: 
  node_type: memory
  type: project
  originSessionId: ef6d0681-d3f3-4528-b218-0de0f03bac72
---

用户要做**全自动**版 bot (新 Polymarket 账户, LLM 全用智谱 GLM, 去掉所有人工)。

**✅ 基础已完成 (2026-07-06)**: `~/polymarket-auto` = 老项目纯代码 fork (已同步到 v7.4.5: 混合型回撤35%砸穿→直接平仓不走重评[07-08晚用户令]; 7.4.4 移动止损; fork 时已含 7.4.1-7.4.3 事件型翻倍优先/0.782保护/-60%入场锚/无未分类) (main.py + 15 modules + data/dino + vendored py_clob_client_v2)。零密钥/零历史/零备份/与老项目零关联 (各自 .env/db/venv/git)。端口 **5052** (老bot 5051)。**入口文件=autobot.py 不叫 main.py** (2026-07-07 结构性防误杀: pkill -f main.py 匹配不到它, 反之亦然, 已 pgrep 实证); 重启用其 restart.sh (LISTEN-only 端口杀)。独立 .venv (python3.12 homebrew; httpx 需配 h2)。实测启动 OK (缺 POLY_* 时只读模式)。GitHub **私有** repo = `RobinVico/polymarket-auto` (唯一 remote origin, 无 cron auto-backup)。临时 DASHBOARD_PASSWORD/FLASK_SECRET_KEY 随机生成在其 .env。

**用户已定 (2026-07-08)**: 请求频率上限=不加; IP 分离=先不动 (讲解过: 首选每进程 HTTPS_PROXY 代理, 等纸上阶段看真实调用量再定)。

**新规则 (2026-07-08 追加)**: ⑤智谱两把 key 分工死规矩 = ZHIPUAI_API_KEY_DISCOVERY 选品 / ZHIPUAI_API_KEY_REEVAL 重评 (autobot 映射给 ZHIPUAI_API_KEY), 绝不混用。⑥每天 10:00 (AUTO_DAILY_REEVAL_HOUR) 24h全仓巡检重评 (✅第2.5步已建: auto_daily_reeval.py, 首次只上膛不补跑)。✅第2步已建: auto_discovery.py (扫描完→GLM选品→无JSON追问一次→auto_candidates 入库→/auto 页, 只列清单不交易)。
**✅ 凭据全通 (2026-07-08 深夜, 一下午侦探战果)**: 新账户=Polymarket 2026「存款钱包」架构 → **必须 POLY_SIGNATURE_TYPE=3 (POLY_1271)** + **py_clob_client_v2 升 1.0.2**(vendored 已换, 1.0.0 填错 order signer)。用户的 funder+私钥从头就是对的; sig=1/2/0 一律余额$0+"maker address not allowed"。链上查钱是死路 (现金内部托管, 老账户$76.85链上也是0)。新CLOB金额规则: 市价买 maker≤2位小数 → executor.buy 打了**整数股数 AUTO 分叉补丁 (同步老项目代码时必须保留)**。
**✅ 真钱闭环测试通过 (2026-07-08)**: bot API 买 美伊核协议 NO 2股@0.89 → 录meta → GLM重评(R key 出合法决策+高质量调研) → force_exit@0.885 → closed_positions/meta清零/现金$48.65 全对, 磨损3分钱。账户现状: $48.65 现金 + 姆巴佩仓 5.27股(用户手买2.27+探针3股, 无meta默认hybrid)。
**⚠️ 重要坑 (第3/4步前必须处理)**: GLM 重评 new_q 方向歧义 — 一次填对持有方向(0.85), 一次填成 YES 方向(0.10 而应为 NO 0.90); 自动执行 update_q 前要加方向翻转嗅探守卫。老项目同 prompt 大概率同病。其余小坑: executor buy 消息把 makingAmount 当股数(显示bug)/不传 neg_risk(多结果市场会失败)/tick_size 写死。
**该repo CLAUDE.md 持续维护 = 单一真相源, 新会话先读它。**

**用户已定的流水线规则 (2026-07-08)**: ①定时扫描 = 每天 09:00/21:00 本机时间 (**✅第1步已上线实测**: modules/auto_scheduler.py, slot 防重放+停机补跑, 27tag/12s)。②GLM 选品: 没返回 JSON → 再发一条消息要 JSON (只追问一次)。③筛选**写死**(否掉 edge/双跑/信心/流动性那套): 推荐现价 0.40<p<0.85 → 按计算器金额真买; 否则 → 自动进测试仓。④测试仓进去后**零操作零重评** (省API; 免费盯价保留)。⑦单tag候选<5个→该tag不送GLM (2026-07-08确认按单标签算, AUTO_DISCOVERY_MIN_CANDIDATES=5; 手动单tag触发不受限; 多数日子可能=零调用, 用户明知)。开发协议见 [[step-by-step-build-protocol]] (一步一报)。
**⬜ 未定规则**: 钱(预算/单仓/日限) / 熔断线+复位方式 / presence旗标 / GLM挂了出场兜底(纯智谱?) / 黑名单 / 通知渠道 / 完整性自检+watchdog。新bot现**在跑**(5052, 只读无钥匙, 每天两扫)。

**🚀 全自动已上线 (2026-07-08 晚, 用户"全部自动现在开始")**: auto_trader.py 第3+4步 = 候选按执行时新鲜价过 40~85 → 真买(公式金额+自动meta) / 测试仓(auto_size)。E2E 实测: Iran YES@0.23→paper $1.94; 法国世界杯 NO(负险!)→真买 5股$3.37 全对。**每日节奏**: 9/21点 扫描→选品(单tag≥5候选才送GLM)→执行; 10点全仓巡检重评; 大跌随时重评; 全部自动执行 (AUTO_FORCE_OFFLINE=1, 开页面不暂停)。
**tags 永远不变 (2026-07-08 用户令)**: 动态热门标签功能在 AUTO 仓库整体删除 (tag_discovery/tag_routes 文件删了, scanner/dashboard 已拆干净, /tags 404); 宇宙=tags.py 白名单, 同步老项目时永不拷回。
**宇宙铁律 (2026-07-08 用户炸锅后加)**: 只能交易「白名单tags扫描报告里真实出现的市场」(_in_universe: tag∈tags.py + slug在报告文件里, 真买/测试仓都管)。事故: Claude E2E 注入体育市场买成真仓→立即清仓+闸门。**永不为测试注入宇宙外市场**。
**守卫已上线**: new_q 方向嗅探→反问 GLM 本人 (确认不了=本轮不动) + prompt 硬化; executor 凑步长数学(任意tick的2位小数maker)+negRisk/tick 自动查; 日买入上限 $10 + 最多 8 仓 (Claude 定的默认, env 可改)。
**账户现状 (07-08 18:05)**: 现金 $47.42 + 法国NO 5股@0.674 (第一个全自动仓位, event_driven) + 测试仓1个; 姆巴佩是用户17:55自己卖的。
**⬜ 未定 (下次商讨, 不阻塞运行)**: 熔断线(日亏≥$X停) / 通知渠道 / watchdog+完整性自检 / GLM挂了出场兜底。老账户照常跑=A/B对照。相关: [[paper-trading-feature]] [[step-by-step-build-protocol]]
