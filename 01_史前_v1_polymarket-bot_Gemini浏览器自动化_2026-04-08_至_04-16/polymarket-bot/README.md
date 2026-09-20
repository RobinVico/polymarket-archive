# Autonomous Polymarket Bot

> An AI-driven automated trading bot for Polymarket prediction markets, using Gemini Deep Research to identify mispriced low-probability events and sentiment-driven price swings.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

---

## ⚠️ Disclaimer / 免责声明

**READ CAREFULLY BEFORE USING THIS SOFTWARE.**

This project is released **for educational and research purposes only**. It is **NOT financial advice** and **NOT intended for production trading with real funds**.

**Risk Warnings:**
- 🔴 **Cryptocurrency and prediction market trading involves substantial risk of loss.** You can lose all of your invested capital.
- 🔴 **Automated trading amplifies risk.** Bugs, API failures, AI misjudgments, or network issues may cause unexpected losses.
- 🔴 **Polymarket access is restricted in some jurisdictions.** Users are responsible for compliance with their local laws.
- 🔴 **This bot uses AI-generated trading decisions.** AI models can be wrong, biased, or hallucinate. Do not trust them blindly.
- 🔴 **No warranty.** The software is provided "AS IS" without warranty of any kind. The author(s) accept NO responsibility for any losses, damages, or legal issues arising from its use.

**If you choose to use this code with real funds, you do so entirely at your own risk.** We strongly recommend starting with paper trading and tiny position sizes.

---

## 🧠 Overview

This bot is designed to autonomously discover and trade mispriced events on Polymarket. Rather than filtering candidate markets with hand-coded rules, it delegates the hard judgment calls to **Gemini Deep Research**, which conducts live web research on each candidate before emitting structured trade recommendations.

**Design Philosophy:**
- **AI-first market discovery** — let Deep Research evaluate markets autonomously
- **Conservative sizing** — fractional Kelly (1/10), daily budget caps, per-bet hard limits
- **Trade, don't hold** — positions are actively managed based on sentiment and price swings rather than held to resolution

---

## 🏗️ Architecture

Six core modules:

| Module | Responsibility |
|--------|---------------|
| `market_scanner.py` | Builds prompts and dispatches candidates to Gemini Deep Research |
| `gemini_driver.py` | Playwright-driven Chrome automation for Gemini's web UI |
| `report_parser.py` | Four-layer fallback JSON extraction with auto-repair |
| `risk_engine.py` | Fractional (1/10) Kelly position sizing |
| `executor.py` | Live order placement via `py-clob-client` |
| `dashboard.py` | Flask dashboard running at `localhost:5050` |

A **position monitor** runs on a 5-minute cycle, triggering AI-reviewed hold/sell/add decisions at >200% profit or >50% loss thresholds.

---

## 📦 Requirements

- **Python 3.12**
- **macOS or Linux** (tested on Mac mini)
- **Chrome browser** with a signed-in Google account for Gemini access
- **Polymarket wallet** with funded Polygon USDC
- **Gemini Advanced subscription** (for Deep Research access)

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/RobinVico/autonomous-polymarket-bot.git
cd autonomous-polymarket-bot
```

### 2. Set up Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure environment variables

Copy the example file and fill in your own credentials:

```bash
cp .env.example .env
nano .env
```

Required variables:
- `POLY_PRIVATE_KEY` — your Polymarket wallet private key
- `POLY_FUNDER` — your funder address
- `POLY_SIGNATURE_TYPE` — set to `1` for Polygon Gnosis Safe
- `POLY_API_KEY`, `POLY_API_SECRET`, `POLY_PASSPHRASE` — generate via `01_setup_check.py`

**⚠️ Never commit your `.env` file. It is already listed in `.gitignore`.**

### 4. Set up Chrome profile for Gemini automation

Google blocks automation on fresh Chrome profiles. You must use a **copy** of your real Chrome profile:

```bash
cp -r ~/Library/Application\ Support/Google/Chrome/Default ~/.polymarket-bot-chrome-profile-copy
```

The Playwright driver loads this profile non-headlessly. **Never run headless** — Google will block sign-in.

### 5. Generate Polymarket API credentials

```bash
python 01_setup_check.py
```

Copy the printed `apiKey / secret / passphrase` values back into your `.env`.

---

## ▶️ Usage

### Read current account state

```bash
python 02_read_state.py
```

### Run the market scanner (dry run)

```bash
python 03_market_watch.py
```

### Start the main trading loop

```bash
python main_loop.py
```

### Start the dashboard

```bash
python -m modules.dashboard
```

Then open http://localhost:5050 in your browser.

---

## ⚙️ Configuration Defaults

| Setting | Default |
|---------|---------|
| AI recommendation frequency | 1 per 5-hour cycle |
| Daily budget cap | $5 |
| Per-bet hard limit | $0.50 – $1.00 |
| Kelly fraction | 1/10 |
| Position review interval | 5 minutes |
| Review trigger (profit) | +200% |
| Review trigger (loss) | -50% |

Adjust these in `modules/risk_engine.py` and `modules/position_monitor.py`.

---

## 🧩 Key Learnings & Design Notes

### Gemini truncation problem
Gemini runs out of output space after long Deep Research reports. The fix is a **two-step flow**:
1. Trigger research and confirm with the Start Research button
2. Send a follow-up message in the same conversation requesting **only** compact JSON

This isolates the structured output from the long analytical text.

### Simplified JSON schema
Output format uses single-line `RESULT_JSON: {...}` with abbreviated fields (`slug`, `mp`, `tp`, `conf`, `reason`) rather than a nested structure. This dramatically reduces truncation risk.

### Resilient parser
Four extraction methods, in order:
1. `RESULT_JSON:` label match
2. Backtick JSON block
3. Bare JSON scan from end of text
4. Keyword extraction fallback

Auto-repair handles common truncation patterns (e.g., `"position_actions":}`).

### Chrome profile handling
- Copied profile required (Google blocks fresh profiles)
- Non-headless mode required (headless is detected and blocked)
- These are **non-negotiable constraints**

### Position review default
Gemini is explicitly instructed to **default to hold** and recommend selling only when fundamentals have fundamentally collapsed. Review history is tracked per position — follow-up AI calls are skipped unless the position moves an additional 30% after a prior hold decision.

---

## 🗂️ Project Structure

```
autonomous-polymarket-bot/
├── modules/
│   ├── browser_manager.py
│   ├── claude_driver.py
│   ├── claude_research.py
│   ├── dashboard.py           # Flask dashboard (main UI)
│   ├── db.py
│   ├── executor.py
│   ├── gemini_driver.py
│   ├── market_scanner.py
│   ├── phase_manager.py
│   ├── position_monitor.py
│   ├── prompts.py
│   ├── report_parser.py
│   └── risk_engine.py
├── 01_setup_check.py          # Generate Polymarket API credentials
├── 02_read_state.py           # Inspect wallet balance & positions
├── 03_market_watch.py         # Market scanner dry-run
├── 04_rules_paper.py          # Paper trading rules test
├── dashboard.py               # Standalone Polymarket data API helper
├── main_loop.py               # Main autonomous trading loop
├── .env.example               # Environment variable template
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🛣️ Roadmap / Known Limitations

- [ ] **Live order placement is untested** with real funds at time of initial release
- [ ] `get_balance()` currently estimates balance by subtracting invested capital from a hardcoded starting value; proper web3 USDC balance querying is planned
- [ ] Geo-blocking handling is external to this codebase
- [ ] Unit tests not yet included

---

## 🤝 Contributing

This is a personal research project, but pull requests are welcome. Please do not submit PRs that:
- Add code enabling abusive trading strategies
- Remove or weaken the risk limits or disclaimers
- Introduce hardcoded credentials

---

## 📜 License

[MIT License](LICENSE) — see LICENSE file for details.

---

## 🙏 Acknowledgments

- [Polymarket](https://polymarket.com/) for the prediction market platform
- [py-clob-client](https://github.com/Polymarket/py-clob-client) for the trading client library
- [Playwright](https://playwright.dev/) for browser automation
- Google Gemini Deep Research for AI-powered market analysis

---

**Built by [@RobinVico](https://github.com/RobinVico)** — for learning and research purposes only.
