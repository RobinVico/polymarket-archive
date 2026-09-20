# Polymarket Semi-Auto Trading System

A semi-automated trading system for [Polymarket](https://polymarket.com) prediction markets.
**Human + AI hybrid**: human places trades, AI (via Claude Research) does analysis, bot handles tier-based take-profit and stop-loss.

> ⚠️ **Disclaimer**: This is research-grade software. Trading prediction markets involves risk of loss. Use at your own risk. The author is not liable for any financial losses.

---

## Design Philosophy

Unlike fully-automated trading bots, this system splits the work:

| Component | Role | Why |
|---|---|---|
| **Scanner** | Pulls markets from Polymarket Gamma API, applies hard filters (price/volume/depth/spread), generates Markdown report | Mechanical filtering of liquidity & dates |
| **Human** | Reviews the scan report, runs Claude Research analysis, decides whether to enter | AI provides analysis, human makes final judgment |
| **Trader (you)** | Manually places limit orders on Polymarket website (as maker, saves taker fee) | Avoids stupid mistakes, captures rebates |
| **Monitor (bot)** | Every 3 minutes checks positions, executes T1/T2/T3 take-profit and W1/W2/W3 reverse-stop-loss tiers | Mechanical execution of pre-defined rules |
| **Re-evaluation** | When a position hits 80% of TP target, dashboard shows yellow alert prompting human to re-run Claude Research | Avoids exiting too early on momentum-driven events |

---

## Architecture
~/polymarket-semi-auto/
├── main.py                  # Entry: starts monitor + Flask
├── .env                     # Credentials (DO NOT commit)
├── semi_auto.db             # SQLite (events / tier_sold / position_meta)
├── bot.log                  # Runtime log
└── modules/
├── dashboard.py         # Flask web UI + API routes
├── scanner.py           # Market scanner + report generator
├── monitor.py           # Position monitor + tier rules
├── executor.py          # CLOB client wrapper (sell with FAK + best_bid)
├── db.py                # SQLite interface
├── prompts.py           # Claude Research prompt templates
└── tags.py              # 22 whitelisted tags + blacklist

---

## Features

### Market Scanner
- **Two scan modes**: keyword search or tag-based discovery (22 whitelisted Polymarket tags grouped by Tier 1/2/3)
- **Three filter ranges** (standard / medium / wide) with progressively relaxed liquidity thresholds
- Hard filters: price range, volume, order book depth, spread, settlement window, ambiguous resolution words
- Dual blacklist (tag-based + keyword-based with word-boundary matching)
- Reports grouped by event for cluster analysis

### Position Monitor
- **Take-profit tiers**: T1/T2/T3 at +5pp/+10pp/+15pp from entry, selling 25%/35%/40% respectively
- **Reverse stop-loss tiers**: W1/W2/W3 with gap-relative dynamic distances
- **Time stop**: ≤2 days to settlement + price barely moved → full exit
- **Small-edge mode**: when gap < 10pp, single exit at mp + min(gap-2, 8pp)
- Direction-unified: both YES and NO positions follow "holding token's price up = profit"

### Sell Execution (Critical)
- Uses FAK (Fill-And-Kill) order type — fills immediately or cancels, never rests
- Pulls best_bid as limit price for slippage protection
- Strictly validates `result.success` AND `makingAmount > 0` (avoids "fake success" bug)
- Logs partial fills as warnings

### Dynamic TP Uplift
- When position hits 80% of TP target, dashboard shows yellow re-eval badge
- One-click prompt copy → paste to Claude Research → choose A (uplift TP) / B (skip) / C (exit early)
- Bot does NOT auto-uplift; human decides based on Claude's findings
- One re-evaluation per position lifetime (status machine: pending → done_*)

### Dashboard
- Tab UI: keyword scan / tag scan
- 22 tag chips colored by Tier (green/blue/purple)
- Position table with TP input + manual save
- Trigger price display: T1/T2/T3 (green) and W1/W2/W3 (red)
- Partial refresh every 30s (no full page reload)
- Real-time log tail

---

## Setup

### Prerequisites
- Python 3.12+
- Polygon wallet with USDC funded on Polymarket
- Polymarket account using EOA, Magic/Email, or Proxy Wallet

### Install

```bash
git clone https://github.com/RobinVico/polymarket-semi-auto.git
cd polymarket-semi-auto

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env with your credentials
```

| Variable | Required | Description |
|---|---|---|
| `POLY_PRIVATE_KEY` | Yes | Wallet private key (0x...) |
| `POLY_FUNDER` | Yes | Funder address (0x...) |
| `POLY_SIGNATURE_TYPE` | Yes | 0=EOA, 1=Magic, 2=Proxy |
| `POLY_API_KEY/SECRET/PASSPHRASE` | No | Auto-generated on first run |

### Run

```bash
# Foreground
python3 main.py

# Background
nohup python3 main.py > output.log 2>&1 &
```

Open http://localhost:5050 in your browser.

---

## Daily Workflow

1. **Scan** — pick a tag or enter keyword, choose range (standard/medium/wide)
2. **Copy prompt to Claude** — click "Copy for Claude" button
3. **Run Claude Research** — paste prompt, wait 5-15 min for analysis
4. **Review recommendation** — Claude outputs human-readable cards (slug / direction / price / raw estimate / calibrated estimate / edge / confidence)
5. **Place order manually** — go to Polymarket website, place Limit order as maker
6. **Save TP** — back in dashboard, fill TP value (calibrated probability) for that position
7. **Bot takes over** — monitors price every 3 minutes, executes T/W tiers automatically

---

## Tag Whitelist

**Tier 1 (11 tags)** — strongest analyst edge
Iran, Israel, Ukraine, Ukraine Peace Deal, Russia, China, Taiwan, Geopolitics, Middle East, World, Foreign Policy

**Tier 2 (10 tags)** — moderate edge
Trump, Trump Presidency, SCOTUS, Politics, US Politics, AI, OpenAI, Tech, Science, Venezuela

**Tier 3 (1 tag)** — reverse-bet (sell NO preferred)
Awards

**Blacklist** — auto-rejected: Crypto/Bitcoin/Ethereum/Solana/Sports/Soccer/NFL/NBA/Hurricane/Weather/Fed/CPI/Inflation/...

---

## Filter Parameters

| Item | Standard | Medium | Wide |
|---|---|---|---|
| Price range | 5%-92% | 4%-93% | 3%-95% |
| 24h volume | ≥$500 | — | — |
| Total volume | — | ≥$2000 | ≥$3500 |
| Depth | ≥$3 | ≥$2.5 | ≥$1.5 |
| Spread | ≤5pp | ≤6pp | ≤8pp |
| Settlement | 5-30d | 4-45d | 3-75d |
| Ambiguous words | strict | strict | strict |

---

## Stop-Loss / Take-Profit Rules

### Take-profit (price moves up)
- **Small edge** (gap < 10pp): single exit at `mp + min(gap-2, 8pp)`
- **Tiered** (gap ≥ 10pp):
  - T1 → `mp + 5pp` sell 25%
  - T2 → `mp + 10pp` sell 35%
  - T3 → `min(mp + 15pp, tp - 2pp)` sell remaining 40%

### Reverse stop-loss (price moves down)
- W1 → `max(5pp, min(gap×0.33, 8pp))` sell 30%
- W2 → `max(10pp, min(gap×0.67, 14pp))` sell 40%
- W3 → `max(15pp, min(gap×1.0, 20pp))` full exit

### Time stop
Distance to settlement ≤ 2 days AND |cur - mp| < 5pp → full exit

---

## API Routes

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Dashboard |
| `/api/control` | POST | scan / scan_tag / check / refresh |
| `/api/snapshot` | GET | Position snapshot for partial refresh |
| `/api/scan_report` | GET | Latest scan markdown |
| `/api/full_prompt` | GET | DISCOVERY_PROMPT + scan report joined |
| `/api/record_position` | POST | Save TP with direction sanity check |
| `/api/update_tp` | POST | Update TP |
| `/api/reeval_prompt` | GET | Generate re-eval prompt for a position |
| `/api/mark_reeval` | POST | Mark uplift / skip / close |
| `/api/logs` | GET | Last 80 lines of bot.log |

---

## Tech Stack

- **Python 3.12** + **Flask** + **SQLite**
- **py-clob-client** for Polymarket CLOB
- **Polymarket Gamma API** for market discovery
- **Claude Research** (via copy-paste, no API integration) for market analysis

---

## Limitations & Trade-offs

- **Manual order entry**: human must place orders on Polymarket website (no auto-buy)
- **Claude Research subscription required** for analysis (Claude Max plan or equivalent)
- **VPN may be required** depending on jurisdiction
- **Maker rebates only on Finance category** in Polymarket — geopolitical/political markets pay full taker fee
- **No portfolio sizing** — designed for fixed-size manual entries (Kelly criterion not implemented)

---

## Documentation

- [Full Technical Documentation (Markdown)](docs/TECHNICAL.md) - System architecture, design rationale, all SL/TP rules, prompt design, bug history
- [Technical Documentation (Word)](docs/Polymarket_Technical_Doc_EN.docx) - Same content in formatted Word document

## License

MIT — see [LICENSE](LICENSE)

---

## Disclaimer

This software is provided as-is. Prediction markets carry financial risk. The author makes no warranty about profitability, accuracy of analysis, or correctness of execution. **Test thoroughly with small amounts before scaling.**
