<div align="right"><b>English</b> | <a href="README.zh.md">中文</a></div>

# Polymarket Fully-Autonomous Trading System (AUTO v8.5.5)

> A zero-human-intervention trading system for Polymarket prediction markets: scheduled scanning → LLM market discovery → hard-coded routing rules → automatic order execution → position monitoring → automatic re-evaluation → automatic exit. The same AI recommendations fed **three live-money accounts** running three different exit strategies. This is the **latest version**; code lives in [`latest_AUTO-v8.5.5_three-account-system/`](latest_AUTO-v8.5.5_three-account-system/).

## How it works

**One fully automatic pipeline** (single process, port 5052):

```
Scheduled scan → LLM discovery → Hard-coded routing → Auto order → Monitoring → Auto re-eval → Auto exit
09:00/21:00      agentic web      0.40<price<0.85     Kelly sizing   every 30s    dip-triggered +    TP / SL /
27 whitelisted   research,        real money, else    + confidence                daily 15:00        re-eval says
tags             JSON output      paper account       multiplier                  full sweep         sell
```

1. **Scan** — twice a day (09:00 / 21:00) across 27 whitelisted tags (`modules/tags.py`); mechanical filters on liquidity / price / dates produce candidate reports.
2. **Discovery** — tags with ≥5 candidates go to Zhipu GLM (a multi-round agentic web-search loop) which returns structured JSON recommendations (side + probability estimate *q* + confidence).
3. **Routing** — hard-coded rule: only fresh quotes between **0.40 and 0.85** are bought with real money; everything else goes to a free paper account. Keyword-blacklisted markets are forced into paper, never real money.
4. **Execution** — quarter-Kelly position sizing (bankroll reference frozen at $50, confidence multiplier ×0.75~1.25, $5 hard cap per position); a final pre-order quote check aborts if the price drifted >3pp.
5. **Monitoring** (pure price logic, zero API cost) — three stop-loss tiers: *convergent* 20% off peak, *hybrid* 35% off peak, *event-driven* hard stop at −50%; confirmed over consecutive ticks, then sold directly. Take-profit ladder: 2× sells all, 0.92 sells half, etc.
6. **Re-evaluation** — an event-driven position that retraces ≥5pp from its best point during the holding period triggers one GLM re-eval; plus a daily 15:00 sweep over all positions. If the re-eval says *exit*, it sells immediately — guarded by a direction-sanity re-ask gate that prevents the LLM from flipping the probability to the wrong side.

**The same recommendations fed three live accounts**, comparing three exit philosophies:

| Account | Exit rule | Entry point |
|---|---|---|
| Main | Full strategy above | `modules/auto_trader.py` + `modules/monitor.py` |
| Bench (baseline) | Take every recommendation; only rule: sell at −30%; otherwise hold to resolution | `modules/auto_bench.py` |
| Shadow (low-price) | Only buy recommendations ≤0.40; −60% stop loss; no take-profit, hold to resolution | `modules/auto_shadow.py` |

Each account has its own monitoring dashboard (`/`, `/bench`, `/shadow`) with equity curves, daily battle reports and a full event stream.

## Running it

```bash
cd latest_AUTO-v8.5.5_three-account-system
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # fill in your own wallet / API credentials (this repo contains no secrets)
bash restart.sh             # entry point: autobot.py, dashboard at http://localhost:5052
```

Notes: Polymarket's 2026 deposit-wallet accounts require `POLY_SIGNATURE_TYPE=3` in `.env`; `py_clob_client_v2` (1.0.2) is vendored in the directory — do not downgrade. At seal time the Zhipu discovery/re-eval keys were deliberately disabled (an upstream search-API change made costs blow up); see the in-directory `CLAUDE.md` for how to re-enable.

## Want the earlier versions and the full iteration history?

Everything is under [`history/`](history/) — **start with the [Project Summary Report (bilingual HTML, EN default)](history/00_final-reports/Project-Summary-Report_2026-09-20_bilingual.html) or the [English PDF](history/00_final-reports/Project-Summary-Report_2026-09-20_EN.pdf)** (full timeline, final three-account results, incident log, lessons learned), then walk the numbered folders: `01` browser-automation prototype (2026-04) → `02` v3 semi-auto initial → `03` semi-auto main project v4–v7 (earlier generations archived inside its `past/`) → `05` early docs & research PDFs → `06` weather-market side project. A bilingual index sits at [`history/README.md`](history/README.md).

## 🔒 Sanitization & disclaimer

This repository is a sealed snapshot: every `.env` / private key / browser session / AI-chat log / runtime log was removed before upload (only `.env.example` templates remain), and every real secret value was verified byte-level absent from the upload set. The project is archived and unmaintained. Trading prediction markets involves substantial risk of loss; nothing here is financial advice.

*Archived 2026-09-20 · RobinVico*
