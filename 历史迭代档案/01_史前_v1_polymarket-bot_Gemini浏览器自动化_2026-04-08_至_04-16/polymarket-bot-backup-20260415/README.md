# Polymarket 全自动交易机器人

## 架构

```
main_loop.py                    ← 主调度器（永不停止）
├── 每5小时 → 扫描 + AI分析 + 下注
├── 每5分钟 → 持仓监控 + 止盈止损
└── Flask dashboard (localhost:5050)

modules/
├── market_scanner.py           ← A: 拉取候选市场 + 组装prompt
├── gemini_driver.py            ← B: Playwright操控Gemini网页版
├── report_parser.py            ← C: 解析AI输出为JSON
├── risk_engine.py              ← D: 1/10凯利 + 硬性封顶
├── executor.py                 ← D: py-clob-client下单/平仓
├── position_monitor.py         ← 持仓盈亏监控
├── dashboard.py                ← Flask仪表盘
└── db.py                       ← SQLite日志
```

## 快速启动

### 1. 安装依赖

```bash
cd ~/polymarket-bot
source .venv/bin/activate
pip install playwright flask requests python-dotenv
playwright install chromium
```

### 2. 首次登录Gemini（只需一次）

```bash
python -c "
from modules.gemini_driver import GeminiDriver
from pathlib import Path
g = GeminiDriver(str(Path.home() / 'Library/Application Support/Google/Chrome'))
g._ensure_browser()
input('在弹出的浏览器中登录Google，完成后按Enter...')
g.close()
print('登录状态已保存')
"
```

### 3. 配置 executor.py

打开 `modules/executor.py`，将占位代码替换成你已跑通的：
- `get_positions()` → 你的 02_read_state.py 逻辑
- `get_balance()` → USDC余额查询
- `place_bet()` → 下单逻辑
- `close_position()` → 卖出逻辑

### 4. 启动

```bash
python main_loop.py
```

打开 http://localhost:5050 查看仪表盘。

## 参数调整

在 `main_loop.py` 顶部：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| SCAN_INTERVAL_HOURS | 5 | AI扫描间隔（小时）|
| MONITOR_INTERVAL_MIN | 5 | 持仓监控间隔（分钟）|
| DAILY_BUDGET_USD | 5.00 | 每日最大花费 |
| MAX_RECOMMENDATIONS | 1 | 每轮AI最多推荐标的数 |
| PROFIT_TRIGGER_PCT | 200 | 盈利多少%触发AI复审 |
| LOSS_TRIGGER_PCT | 50 | 亏损多少%触发AI复审 |

## 凯利公式说明

使用 **1/10 Kelly** 而非 1/4：
- $50账户，1/10 Kelly对3%→10%的标的 ≈ $0.50-$0.90
- 硬性上限: $1.00/笔
- 硬性下限: $0.50/笔（Polymarket最低限额）
- 每日上限: $5.00

## 文件说明

- `bot.log` — 运行日志
- `trading_bot.db` — SQLite数据库（交易记录、事件日志）
- `reports/` — Gemini原始报告存档
- `debug_*.png` — 自动化出错时的截图
