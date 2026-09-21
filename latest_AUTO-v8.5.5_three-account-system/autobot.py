#!/usr/bin/env python3
"""Polymarket AUTO (全自动账户版) — 入口. 2026-07-06 fork 自 ~/polymarket, 独立账户/独立 .env/端口 5052."""
import threading
import logging
from modules.version import VERSION  # v7.x (#1): 单一版本号来源
from dotenv import load_dotenv
load_dotenv()  # 本目录 .env (全部凭据都在这一份: POLY_* / 智谱两把 key / DASHBOARD_PASSWORD / FLASK_SECRET_KEY)
# 🔑 智谱 key 分工 (用户 2026-07-08 定): 选品用 ZHIPUAI_API_KEY_DISCOVERY (auto_discovery.py 直接读);
# 重评用 ZHIPUAI_API_KEY_REEVAL → 这里映射给老代码 auto_reeval 读的 ZHIPUAI_API_KEY, 不改同步来的模块。
import os as _os
if _os.environ.get("ZHIPUAI_API_KEY_REEVAL") and not _os.environ.get("ZHIPUAI_API_KEY"):
    _os.environ["ZHIPUAI_API_KEY"] = _os.environ["ZHIPUAI_API_KEY_REEVAL"]
# v5.10.2: 本机系统 DNS (Tailscale 上游) 对 *.polymarket.com 间歇性污染 (解析到 FB/Dropbox 假 IP),
# 必须在任何 polymarket 连接建立前打 DNS guard (DoH 优先). 详见 modules/gamma_client.py.
from modules.gamma_client import install_polymarket_dns_guard
install_polymarket_dns_guard()
from modules.db import init_db
from modules.monitor import PositionMonitor
from modules.dashboard import create_app, set_monitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()])
log = logging.getLogger("main")

if __name__ == "__main__":
    # 审查修复⑬ (2026-07-08): 两把智谱 key 隔离加固 + 模型环境自检。
    # - 环境里若混进一个别的 ZHIPUAI_API_KEY → 强制覆盖成 REEVAL 专用 key (智谱后台分开记账绝不串)。
    # - 环境里若出现 ANTHROPIC_API_KEY → 重评权威会切 Claude 且默认双跑双花钱, 大声提醒 (用户要纯智谱)。
    _rk = (_os.environ.get("ZHIPUAI_API_KEY_REEVAL") or "").strip()
    if _rk and _os.environ.get("ZHIPUAI_API_KEY") != _rk:
        log.warning("环境里另有 ZHIPUAI_API_KEY (≠REEVAL 专用 key), 已强制覆盖为 REEVAL key — 两把 key 绝不混用")
        _os.environ["ZHIPUAI_API_KEY"] = _rk
    # 用户 2026-07-08 拍板: GLM 主用, Claude 只当"GLM 挂了"的兜底 → 需要 AUTO_REEVAL_PRIMARY=glm + AUTO_REEVAL_DUAL=0。
    # (老代码默认 PRIMARY=claude + DUAL=1 = Claude 权威 + 每次双跑双花钱, 配了 Claude key 却没配这两项就大声骂。)
    _prim = (_os.environ.get("AUTO_REEVAL_PRIMARY") or "claude").strip().lower()
    _dual = (_os.environ.get("AUTO_REEVAL_DUAL") or "1") not in ("0", "false", "False", "")
    if _os.environ.get("ANTHROPIC_API_KEY"):
        if _prim != "glm" or _dual:
            log.warning(f"⚠️ ANTHROPIC_API_KEY 已配, 但编排不是「GLM主用+串行兜底」(PRIMARY={_prim}, DUAL={int(_dual)}) "
                        "→ 会主用 Claude / 每次双模型双花费! 用户拍板配置 = AUTO_REEVAL_PRIMARY=glm + AUTO_REEVAL_DUAL=0")
        else:
            log.info("重评编排 ✓: GLM 主用, Claude 兜底 (仅 GLM 挂时才调用, 平时零 Claude 花费)")
    elif _prim == "glm" and not _dual:
        log.info("重评编排: 纯 GLM (未配 ANTHROPIC_API_KEY, GLM 挂时该轮重评失败等下轮; 配上 key 即自动获得 Claude 兜底)")
    init_db()
    # 部署后 seed 一行 portfolio_snapshot,避免首次打开图表为空
    # 守卫: 跟 monitor.py check_once 一致 — positions=[] AND cash=0 几乎肯定 API 失败
    # (geoblock / 网络抖动), 跳过 seed 避免写一行全 0 污染曲线.
    try:
        import time
        from modules.executor import Executor
        from modules.db import save_portfolio_snapshot
        _exe = Executor.get()
        _pos = _exe.get_positions() or []
        _cash = _exe.get_cash_balance()
        if not _pos and (_cash is None or _cash == 0):
            log.warning("skip seed portfolio_snapshot: positions=[] AND cash=0 (likely API failure)")
        else:
            _tv = sum((p.get("cur_price") or 0) * (p.get("size") or 0) for p in _pos)
            _tc = sum((p.get("avg_price") or 0) * (p.get("size") or 0) for p in _pos)
            save_portfolio_snapshot(int(time.time()), _tv, _tc, _cash, _tv - _tc, _tv + _cash)
            log.info(f"seeded portfolio_snapshot: value=${_tv:.2f} cost=${_tc:.2f} cash=${_cash:.2f}")
    except Exception as e:
        log.warning(f"seed snapshot failed: {e}")
    monitor = PositionMonitor()
    set_monitor(monitor)
    app = create_app()
    log.info(f"=== Polymarket v{VERSION} ===")
    log.info("Dashboard: http://localhost:5052 (AUTO 全自动账户)")
    log.info("Monitor: 每 30 秒 | TP: 事件型 翻倍(2×avg)先到则全卖, 否则0.92卖半(后半跌<0.78再卖)/收敛≤3天 0.88/其余 0.90 或 +100% | SL: 收敛=回撤20%(≤3天12%)+确认→【直接平仓】(AUTO 2026-07-18, 不再交重评) / 混合=回撤35%+确认→直接平仓 / 事件=-50%强行止损【直接平仓·任何东西越不过】+$0.05地板 / 事件盘中另: 从最好点回撤≥5pp触发1次重评(exit护栏已删,说卖立刻卖); 每天15:00全仓巡检照旧 / 未分类当混合")
    threading.Thread(target=monitor.run_loop, daemon=True).start()
    from modules.auto_discovery import register_routes
    register_routes(app)   # /auto 候选清单页 + 手动触发 API (不改 dashboard.py)
    from modules.auto_daily_reeval import register_routes as register_reeval_routes
    register_reeval_routes(app)   # 24h 全仓巡检的手动触发 API
    from modules.auto_trader import register_routes as register_trader_routes
    register_trader_routes(app)   # 第3+4步执行器的手动触发 API
    # 全自动监控主页 (用户 2026-07-09 重做界面): 独立新文件, dashboard.py 一个字不改 (隔离铁律)。
    # `/` 覆盖成监控页 (老半自动 index 代码留着不再被访问); /panel /api_reeval 半自动页跳回 `/`.
    from modules.auto_dashboard import register_routes as register_monitor_routes
    _monitor_view = register_monitor_routes(app)   # /monitor + /api/auto/monitor
    app.view_functions["index"] = _monitor_view    # `/` → 监控主页
    # 往期仓位监测 v2 (2026-07-20): 仓位卡片默认折叠 (标题去码+盈亏, 详情按钮展开)。独立新文件覆盖 /history。
    from modules.auto_history import register_routes as register_history_routes
    app.view_functions["history_page"] = register_history_routes(app)  # /history → 折叠版
    from flask import redirect as _redirect
    def _to_home():
        return _redirect("/")
    for _ep in ("panel_page", "api_reeval_page"):  # 副屏总控台 + Claude/GLM对比页, 用户点名删
        if _ep in app.view_functions:
            app.view_functions[_ep] = _to_home
    log.info("监控主页已挂载: / → 全自动监控 (老 index/panel/api_reeval 半自动页已下线)")
    # Bench 第二账户基准策略 (2026-07-23 用户拍板): 同一份选品推荐, $2/仓·-30%即卖·无重评·持有到结算,
    # 纯测 AI 准确率。⚠️ start_bench 必须在主线程、app.run 之前跑 (env 临时换 BENCH_POLY_* 构造第二个
    # Executor 实例, 避开运行时读 POLY_FUNDER 的竞态); 未配置自动跳过, 主账户/主策略零影响。
    from modules.auto_bench import register_routes as register_bench_routes, start_bench
    register_bench_routes(app)   # /api/bench/* (summary/consume_now/score_now)
    from modules.auto_bench_dashboard import register_routes as register_bench_dash
    register_bench_dash(app)     # /bench 独立监控页 (2026-07-24 用户要求, 设计同全自动主页)
    start_bench()
    # 三号账户 shadow (2026-07-24 用户拍板): 测试仓那半推荐(≤0.40)在第三个账户真买, $2/仓,
    # 止损(-60%+$0.05地板)不止盈、无重评, 拿到结算。跟 bench 同一套隔离模式 (env交换第二实例,
    # 必须主线程 app.run 之前); .env 没配 SHADOW_POLY_* 就待命, SHADOW_DRY_RUN=1 可先空跑。
    from modules.auto_shadow import register_routes as register_shadow_routes, start_shadow
    register_shadow_routes(app)   # /api/shadow/status + /api/shadow/scan_now
    from modules.auto_shadow_dashboard import register_routes as register_shadow_dash
    register_shadow_dash(app)     # /shadow 独立监控页 (2026-07-24 用户要求, 主页克隆换数据源同 /bench)
    start_shadow()
    from modules.auto_scheduler import start_scheduler
    start_scheduler()
    app.run(host="127.0.0.1", port=5052, debug=False)
