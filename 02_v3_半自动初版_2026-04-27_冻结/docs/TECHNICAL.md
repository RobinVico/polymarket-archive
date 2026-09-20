# Polymarket Semi-Auto Trading System — Technical Documentation

**Version**: v3.x · Human + Claude + Tag-Based Discovery
**Stack**: Python 3.12 · Flask · SQLite · py-clob-client

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Market Scanner](#3-market-scanner)
4. [Tag Scanning (Domain-Based Discovery)](#4-tag-scanning-domain-based-discovery)
5. [Stop-Loss / Take-Profit Rules](#5-stop-loss--take-profit-rules)
6. [Dynamic TP Uplift Mechanism](#6-dynamic-tp-uplift-mechanism)
7. [Order Placement & Execution](#7-order-placement--execution)
8. [Claude Research Prompt Design](#8-claude-research-prompt-design)
9. [Dashboard](#9-dashboard)
10. [API Routes](#10-api-routes)
11. [Setup & Daily Use](#11-setup--daily-use)
12. [Design Trade-offs & Known Limits](#12-design-trade-offs--known-limits)

---

## 1. System Overview

### 1.1 Project Positioning

This is a **semi-automated** Polymarket trading system running locally on a Mac. Unlike traditional quant systems, the design philosophy here is **not** to chase fully-automated AI decisions and browser-driven order placement. Instead, the trade actions requiring genuine judgment are reserved for the human and Claude Research, while the system handles only the parameterizable parts: market scanning, position monitoring, and rule-based stop-loss / take-profit execution.

### 1.2 Runtime Environment

| Item | Value |
|---|---|
| Host | Mac (local) |
| Python version | 3.12 |
| Project path | `~/polymarket-semi-auto` |
| Virtual env | `.venv` (venv) |
| Dependencies | py-clob-client · Flask · SQLite · requests · python-dotenv |
| Chain | Polygon (chainId=137) |
| Signature type | `POLY_SIGNATURE_TYPE=1` (Magic/Email Wallet) |

### 1.3 Core Workflow

| # | Actor | Action |
|---|---|---|
| 1 | System | Dashboard scans Polymarket: keyword or tag, with three-tier filter parameters (standard / medium / wide) producing markdown reports |
| 2 | Human | Click "Copy for Claude" in dashboard — copies prompt + latest report in one shot |
| 3 | Claude Research | Receives prompt, outputs bull/bear analysis + raw estimate + calibrated estimate per candidate market, finally a human-readable recommendation card |
| 4 | Human | Reads Claude's recommendation, decides whether to enter and how much |
| 5 | Human | Manually places order on Polymarket website |
| 6 | Human | Fills the TP value (calibrated probability) on the corresponding row in dashboard, clicks save |
| 7 | System | Every 3 minutes checks positions, executes T/W tiers automatically by rule |

---

## 2. Architecture

### 2.1 File Structure

```
~/polymarket-semi-auto/
├── main.py                  # Entry: starts monitor + Flask
├── .env                     # Wallet credentials & API keys
├── semi_auto.db             # SQLite (events / tier_sold / position_meta)
├── last_scan.md             # Latest scan report cache
├── bot.log                  # Runtime log
└── modules/
    ├── dashboard.py         # Flask web UI + API routes
    ├── scanner.py           # Market scanner + report generator
    ├── monitor.py           # Position monitor + SL/TP rules
    ├── executor.py          # CLOB client wrapper (positions + sell)
    ├── db.py                # SQLite interface
    ├── prompts.py           # Claude Research prompt templates
    └── tags.py              # 22-tag whitelist + blacklist
```

### 2.2 Module Responsibilities

| Module | Lines | Responsibility |
|---|---|---|
| `main.py` | ~22 | Process entry. Initializes SQLite, instantiates PositionMonitor, starts background monitor thread + Flask web (port 5050) |
| `modules/dashboard.py` | ~750 | Flask web app + all API routes. HTML/CSS/JS lives here too (string template) |
| `modules/scanner.py` | ~770 | Polymarket Gamma API client. `fetch_markets` / `scan_and_report` (keyword) / `scan_by_tag` (tag) + report generation |
| `modules/monitor.py` | ~250 | `PositionMonitor` class. Loops checking positions, decides whether to trigger T1/T2/T3 or W1/W2/W3 or time-stop, calls `Executor.sell()` |
| `modules/executor.py` | ~190 | py-clob-client singleton wrapper. `get_positions()` query + `sell()` order placement (FAK + best_bid + strict validation) |
| `modules/db.py` | ~110 | SQLite schema + CRUD. Three tables: events / tier_sold / position_meta |
| `modules/prompts.py` | ~60 | DISCOVERY_PROMPT + REEVAL_PROMPT templates. Three-tier edge thresholds (8/12/15pp) |
| `modules/tags.py` | ~190 | 22 whitelisted tags (label/slug/tier/research_hint) + tag blacklist + keyword blacklist |

### 2.3 Database Schema

#### `events` table

Records all trade and scan events. Used for audit and the dashboard event panel.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key auto-increment |
| `timestamp` | TEXT | ISO 8601 timestamp |
| `event_type` | TEXT | scan / scan_tag / sell / buy / etc. |
| `market_slug` | TEXT | Market slug (or tag name) |
| `detail` | TEXT | Detail text |

#### `tier_sold` table

Records which tiers each position has triggered. Avoids re-triggering the same tier.

| Column | Type | Description |
|---|---|---|
| `token_id` | TEXT | Polymarket token ID (long numeric string) |
| `tier_name` | TEXT | T1 / T2 / T3 / SMALL_EXIT / W1 / W2 / W3 / TIME_STOP |
| `timestamp` | TEXT | Trigger time |

#### `position_meta` table

Position metadata. After manual order placement, the user fills TP in dashboard. Stores "entry price mp" and "target price tp" so monitor can compute trigger prices.

| Column | Type | Description |
|---|---|---|
| `token_id` | TEXT (PK) | Position token ID |
| `market_slug` | TEXT | Market slug |
| `side` | YES / NO | Position direction |
| `entry_price` | REAL | Entry price mp (held token's purchase price) |
| `tp` | REAL | Initial target price (held token's target price) |
| `target_gap` | REAL | tp - mp (computed at order time) |
| `end_date` | TEXT | Market settlement date |
| `initial_size` | REAL | Initial position size |
| `new_tp` | REAL | Updated TP (overrides `tp` if set) |
| `tp_updated_at` | TEXT | TP last update time |
| `created_at` | TEXT | Record creation time |
| `notes` | TEXT | User notes |
| `entry_reason` | TEXT | Entry rationale (optional, injected into reeval prompt) |
| `claude_raw_estimate` | REAL | Claude raw estimate (pre-shrinkage, optional) |
| `reeval_status` | TEXT | pending / done_uplift / done_skip / done_close |
| `reeval_at` | TEXT | Reeval action time |
| `reeval_new_tp` | REAL | New TP after uplift (uplift action only) |
| `reeval_action` | TEXT | uplift / skip / close raw record |

---

## 3. Market Scanner

The scanner pulls market data from Polymarket Gamma API, applies hard filters, and generates a markdown report for Claude Research consumption. It does **not** participate in trade decisions.

### 3.1 Three-Tier Filter Parameters (FILTERS)

The scanner offers three filter tiers to adapt to varying market activity. When the narrow tier returns nothing, fall back to wider tiers.

| Filter Item | Standard | Medium | Wide |
|---|---|---|---|
| YES price | 5% – 92% | 4% – 93% | 3% – 95% |
| 24h volume | ≥ $500 | not enforced | not enforced |
| Cumulative volume | not enforced | ≥ $2000 | ≥ $3500 |
| Order book depth | ≥ $3 | ≥ $2.5 | ≥ $1.5 |
| Bid-ask spread | ≤ 5pp | ≤ 6pp | ≤ 8pp |
| Settlement min | 5 days | 4 days | 3 days |
| Settlement max | 30 days | 45 days | 75 days |
| Ambiguous words | strict | strict | strict |

*Ambiguous-word blacklist (rejected in all tiers)*: `likely`, `roughly`, `approximately`, `or equivalent`, `substantial`, `significant`. These words in resolution rules signal UMA may report 0.5.

### 3.2 Scanner Functions

| Function | Purpose |
|---|---|
| `fetch_markets(keyword, cfg)` | Pulls all markets (5000) from Gamma API, applies price/volume/settlement-date/ambiguous filters |
| `check_orderbook_quality(market, clob, cfg)` | Queries CLOB order book, checks spread and depth |
| `scan_and_report(keyword, mode)` | Keyword scan entry. mode = standard / medium / wide |
| `scan_by_tag(tag_label, mode)` | Tag scan entry. Internally calls `fetch_events_by_tag(slug)` |
| `fetch_events_by_tag(tag_slug, limit)` | Calls `/events?tag_slug=X` to pull events under that tag (with embedded markets) |
| `generate_report(...)` | Keyword report generator. Header differs by mode (standard / medium / wide) |
| `generate_tag_report(...)` | Tag report generator. Additionally groups by event for cluster analysis |

---

## 4. Tag Scanning (Domain-Based Discovery)

### 4.1 Design Motivation

Keyword scanning relies on user-guessed words appearing in market descriptions — easily off-target. Polymarket has a native tag system curated by the editorial team (Iran / Trump / Awards etc.). Using tags directly hits the domain accurately and reduces noise.

### 4.2 API Discovery & Mapping

Polymarket Gamma API runtime quirks:

- `GET /tags` returns low-quality tags, **different data source** from what events actually use
- `GET /events` returns event objects whose `tags` field reflects actual usage
- `GET /events?tag_slug=iran` filters correctly. **Only `tag_slug` works** — `tag` / `tagSlug` / `tag_label` / `tag_id` all return 200 but no filtering

At deployment, we reverse-mapped tag label → slug from 1000 active events. All 22 whitelisted tags found their slugs.

### 4.3 22 Whitelisted Tags (by Tier)

#### Tier 1 — Strongest Edge (11 tags)

| Label | Slug | Specialized Hint Summary |
|---|---|---|
| Iran | `iran` | Persian/Hebrew primary sources are alpha. Distinguish 'halt' vs 'suspend' vs 'reduce' in resolution |
| Israel | `israel` | IDF official statements vs media reports; 'attack' boundary (direct strike vs proxy vs cyber) |
| Ukraine | `ukraine` | Distinguish 'framework agreement' / 'signed' / 'actual ceasefire'; Trump-Zelensky minerals deal is a classic trap |
| Ukraine Peace Deal | `ukraine-peace-deal` | Legal wording of ceasefire decides resolution; pick max-edge market |
| Russia | `russia` | Frequently clusters with Ukraine; Putin public statements often diverge from action |
| China | `china` | Chinese primary sources (People's Daily, Xinhua); retired PLA think tanks are leading indicators |
| Taiwan | `taiwan` | Taipei United Daily; military exercise vs invasion vs blockade boundaries |
| Geopolitics | `geopolitics` | Widest scope; group by event then cluster |
| Middle East | `middle-east` | Covers Iran/Israel/Saudi; proxy conflict vs direct strike boundary |
| World | `world` | Largest scope, may have noise; prioritize high-volume events |
| Foreign Policy | `foreign-policy` | US State Dept statements, White House readouts are core |

#### Tier 2 — Moderate Edge (10 tags)

| Label | Slug | Specialized Hint Summary |
|---|---|---|
| Trump | `trump` | Wide scope, group by event for cluster |
| Trump Presidency | `trump-presidency` | Read executive order text; signed vs effective are different triggers |
| SCOTUS | `scotus` | SCOTUSblog, oyez.org, case argument transcripts |
| Politics | `politics` | Huge scope (576 events); prefer specific events |
| US Politics | `us-politics` | Watch state-level polling, whip count |
| AI | `ai` | Beware insider front-running (GPT-5.5 priced 78% three weeks before launch — real case) |
| OpenAI | `openai` | OpenAI official blog + GitHub are leading indicators; announce/release/available distinct |
| Tech | `tech` | Overlaps with AI/OpenAI; differentiate by event |
| Science | `science` | Peer-reviewed results are gold standard; preprints don't count |
| Venezuela | `venezuela` | Spanish primary sources + State Dept; recognition of victory vs actual transfer of power |

#### Tier 3 — Reverse-Bet (1 tag) — Sell NO Preferred

| Label | Slug | Specialized Hint Summary |
|---|---|---|
| Awards | `awards` | [REVERSE] This category systematically over-confident; prioritize selling NO. Read Variety / Hollywood Reporter / Academy committee composition. News actually hurts accuracy here |

### 4.4 Blacklist (Two-Layer)

#### Tag blacklist (any hit → skip entire market)

- **Finance & crypto**: Crypto, Bitcoin, Ethereum, Solana, Crypto Prices, Big Tech, IPOs, Stocks, Finance, Business, Economy, Fed, CPI, Inflation
- **Sports**: Sports, Soccer, NFL, NBA, NHL, MLB, Tennis, Golf, EPL, FIFA World Cup
- **Other irrelevant**: Hurricane, Weather, Earn 4%, 5M, Pre-Market, Hide From New, Recurring, Yearly, Up or Down, Hit Price

#### Keyword blacklist (content fallback, word-boundary regex match)

Keywords: `bitcoin`, `btc`, `ethereum`, `solana`, `hurricane`, `fed rate`, `cpi`, `inflation`, `treasury yield`

> **Important design point**: The keyword blacklist uses `\b...\b` regex word-boundary matching. The naive substring approach caused a critical bug: `"sol"` substring-matched the `"sol"` inside `"resolution"`, killing all 411 Iran-tagged markets in a scan. Fixed via regex.

### 4.5 Tag Report Structure (Grouped by Event)

Unlike the keyword scan, tag scan reports group markets by event. Multiple markets under the same event form a cluster — Claude is instructed in the prompt to "recommend only the single highest-edge market per cluster".

---

## 5. Stop-Loss / Take-Profit Rules

### 5.1 Core Decision Variables

All trigger logic is built on two variables:

- `mp` = position entry price (held token's purchase price, **not** YES price)
- `tp` = user's estimate of "true probability of held direction" = target token price
- `gap_pp` = (tp - mp) × 100 = expected profit space in percentage points

> **Important fix history**: Earlier versions wrongly handled NO position direction, using `sign = -1` to make NO positions "take-profit downward, stop-loss upward". This is wrong. On Polymarket, YES and NO positions are symmetric: holding token's price up = profit. Current version unifies as "take-profit upward, stop-loss downward" regardless of YES/NO.

### 5.2 Take-Profit Rules

#### Small edge (gap < 10pp): Single full exit

Tiered selling at small gap would push the trigger price above tp. Switch to single exit.

| Item | Formula |
|---|---|
| Trigger price | `mp + max(3pp, min(gap-2, 8pp))` |
| Action | Sell all |
| Tier name | SMALL_EXIT |

#### Large edge (gap ≥ 10pp): Three-tier exit

| Tier | Trigger price | Sell ratio (of original) |
|---|---|---|
| T1 | `mp + 5pp` | 25% |
| T2 | `mp + 10pp` | 35% |
| T3 | `min(mp + 15pp, tp - 2pp)` | 40% (remaining) |

The `min` cap on T3 prevents "T3 exceeds tp" when gap is very large: as price approaches tp, lock in profit instead of getting greedy.

### 5.3 Reverse Stop-Loss Three Tiers

When price moves down, don't dump all at once — sell incremental portions to give the market room to recover. Trigger distance scales with gap, but bounded by floor and ceiling.

| Tier | Trigger distance formula | Sell ratio |
|---|---|---|
| W1 (light) | `max(5pp, min(gap × 0.33, 8pp))` | 30% of original |
| W2 (medium) | `max(10pp, min(gap × 0.67, 14pp))` | 40% of original |
| W3 (heavy) | `max(15pp, min(gap × 1.0, 20pp))` | Remaining (full exit) |

#### Example (gap = 22pp position)

| mp | tp | gap | T1 | T2 | T3 | W1 | W2 | W3 |
|---|---|---|---|---|---|---|---|---|
| 73% | 95% | 22pp | 78% | 83% | 88% | 65.7% | 59% | 53% |

### 5.4 Time Stop

Full exit when **both** conditions met (regardless of P&L):

- Distance to settlement ≤ 2 days
- |cur_price - mp| < 5pp (barely moved)

Logic: settling soon but price didn't move = market disagrees with you, output probability is high. Take partial principal back early.

---

## 6. Dynamic TP Uplift Mechanism

### 6.1 Design Motivation

The three-tier take-profit and three-tier stop-loss have an edge case: when Claude's judgment is increasingly correct, price reaches 80% of original TP target but is still far from original TP, the original estimate may have been too conservative. If significant new information supports "true probability could be even higher", the original three tiers will exit too early and miss further upside.

The dynamic TP uplift mechanism solves this: when position reaches 80% progress, dashboard shows yellow alert prompting human to re-evaluate via Claude Research. Claude returns A/B/C, human manually clicks menu to apply. **Bot does not auto-uplift TP, does not auto-sell.**

### 6.2 Trigger Conditions (4 conditions, all must hold)

| # | Condition | Note |
|---|---|---|
| 1 | `progress ≥ 0.80` | `(cur - entry) / (tp - entry) ≥ 80%`, all using held token price |
| 2 | `days_to_resolution ≥ 5` | Still time to ferment, too close to settlement = no upside room |
| 3 | `size > 0` | Position has remaining (implicitly covers "T3 not triggered") |
| 4 | `reeval_status = 'pending'` | Never prompted before — once per position lifetime |

> Edge case: For very large edges (gap ≥ 30pp), 80% progress corresponds to price moving past mp+24pp, by which time T3 (mp+15pp or tp-2pp) has already triggered and the position is cleared. In this case the mechanism never triggers, which is **intended behavior** — super-large gaps already captured the bulk via tiers, no need to uplift TP.

### 6.3 UI Three-State Badge

| Status | Display | Clickable |
|---|---|---|
| Not triggered | (no badge) | — |
| `pending + should_reeval=true` | ⚠️ Yellow `Progress X% Reeval TP ▾` (pulsing) | Yes |
| `done_uplift` | Gray `✓ Reevaluated (uplifted to X%)` | No |
| `done_skip` | Gray `Skipped reeval` | No |
| `done_close` | Gray `Reevaluated → close` | No |

### 6.4 Human Workflow (yellow badge to completion)

1. Position price reaches 80% progress → yellow badge appears automatically
2. Click yellow badge → expands menu (with "Copy prompt" + A/B/C three options)
3. Click "Copy Claude Prompt" → fetches `/api/reeval_prompt` → fully-populated prompt copied to clipboard
4. Paste to Claude.ai Research mode → wait 5–15 minutes
5. Claude returns A/B/C with rationale
6. Back in dashboard, click same yellow badge to expand menu, choose A/B/C per Claude's result:
   - **A**: Enter new TP number (e.g. 95) → click "✓ Apply" → POST `/api/mark_reeval action=uplift` → badge turns gray `✓ Reevaluated (uplifted to 95%)` → tier triggers recalculate
   - **B**: Click "Skip" → `action=skip` → TP unchanged, continue with original tiers, badge turns gray
   - **C**: Click "Exit early" → confirm dialog reminds "bot won't auto-sell" → `action=close` → human goes to Polymarket to manually sell, badge turns gray

### 6.5 Reeval Prompt Design Points

`REEVAL_PROMPT` lives in `modules/prompts.py`, total length ~1400 chars. Six design points:

| # | Point | Motivation |
|---|---|---|
| 1 | Explicitly tell Claude to use Research mode for primary sources | Avoid relying solely on training data (would make reeval pointless) |
| 2 | Inject `entry_reason` (optional) | Claude can judge whether original logic still holds |
| 3 | Mark Option B as default | Counter LLM bias of being "framing-induced toward aggressive answers" |
| 4 | Option A requires ≥2 specific new info items + source + date | Prevent momentum thinking ("price went up so I was right") |
| 5 | Option A requires annualized IRR calculation | Prevent capital being tied up in low-IRR opportunities |
| 6 | Strictly structured output (4 sections) | Quick decision read at a glance |

### 6.6 New API Routes

| Route | Method | Purpose |
|---|---|---|
| `/api/reeval_prompt?token_id=X` | GET | Fetch fully-populated reeval prompt for a position |
| `/api/mark_reeval` | POST | Mark reeval result. body: `{token_id, action: uplift\|skip\|close, new_tp?}` |

#### Discipline-to-Code Mapping

| Discipline | How Code Enforces |
|---|---|
| Must have real new info to uplift | Prompt forces Option A to list ≥2 new info items + source + date |
| Uplift at most once | `reeval_status` state machine: pending → done_*; can't return to pending |
| Uplift cap 99% | Prompt explicit + UI input `max=99` + backend `mark_reeval` checks `0 < new_tp < 1` |
| Reeval triggers only once | `should_reeval = (status==pending) AND ...other`. Once status set, irreversible |

---

## 7. Order Placement & Execution

### 7.1 Manual Order Placement Workflow

All buying is done by human on Polymarket website — bot does not participate in buying. Recommended order placement:

1. Select market on Polymarket page, click Buy
2. Switch to Limit tab (limit order, **as maker** — do not click Market)
3. Place price one tick above current best ask (e.g., if others quote 0.27, you quote 0.27 or better), enter ask queue
4. Wait for taker to eat your order — this way you're maker, save ~1.12% taker fee, and on Finance category you can collect 50% rebate

After ordering, return to dashboard, fill TP value (Claude's calibrated estimate) on that position row, click save. System immediately computes T1/T2/T3 and W1/W2/W3 trigger prices.

> **Boundary protection**: Saving TP in dashboard has direction validation — `tp` must be `> entry_price`. If you fill incorrectly (e.g. NO position with YES-perspective probability), the save is rejected. This caught the historical "direction reversed" bug.

### 7.2 Auto-Sell Logic (`executor.sell`)

Selling is the only trade action automated by the system. To avoid the historical "thought it sold but didn't" bug, current sell logic strictly checks:

#### Steps

1. **Parameter check**: round `size` to 2 decimals (Polymarket SELL precision limit); skip if < 0.01
2. **Pull order book** (`get_order_book`), check best bid exists
3. **Take best_bid as limit price** (slippage protection)
4. Construct `OrderArgs(price=best_bid, size, SELL)` + `OrderType.FAK`
5. Call `client.create_order()` then `client.post_order(signed, OrderType.FAK)`
6. **Strict return validation**: only `result.success` AND `makingAmount > 0` counts as real fill
7. Partial fill (`makingAmount < size × 0.95`) still returns True but logs WARNING

#### Why FAK over GTC

- **FAK** = Fill And Kill, fills what it can immediately and cancels the rest. Guaranteed to never rest on the book.
- Earlier version used `OrderArgs(price=0.01)` defaulting to GTC, but didn't check API rejection equivalent to silent error — root cause of the historical "fake success" bug.
- `price = best_bid` is the upper bound — protects against being filled at malicious low bids.

### 7.3 Production Verification Example

Real production log of W2 reverse-stop-loss firing successfully (anonymized timestamps):

```
[T+00:00] 3 positions
[T+00:00] → WARNING2_40: <market title>
            sell=<size> | W2: price$0.445 broke through $0.460 (-10.0pp) sell 40%
[T+00:00] SELL token=<token_id> size=<size> best_bid=$0.4200
[T+01s] HTTP POST /order → 200 OK
[T+01s] sell raw result: {
    'errorMsg': '',
    'orderID': '0x<order_hash>',
    'takingAmount': '0.2982',  // USDC received
    'makingAmount': '<size>',  // shares sold
    'status': 'matched',
    'transactionsHashes': ['0x<tx_hash>'],
    'success': True
}
[T+01s] sell success: status=matched
```

#### Analysis

- Price dropped to 0.445, hit W2 trigger 0.460 (entry - 10pp)
- 40% of original size sold via best_bid limit at 0.42
- USDC actually received = size × 0.42
- W3 would fire at 0.40 if price continued falling (not reached in this case)

This single event verified end-to-end: monitor detection → executor.sell → CLOB API → on-chain settlement.

---

## 8. Claude Research Prompt Design

### 8.1 Core Design Ideas

The discovery prompt has three key mechanisms, all aimed at reducing Claude's overconfidence:

#### Mechanism 1: Dual Estimate + Shrinkage Toward Market

Claude outputs two probabilities:

- **Raw estimate**: Claude's independent judgment of true probability
- **Calibrated estimate** = `market_price + 0.5 × (raw - market_price)`

Meaning: split the difference 50/50 between Claude and the market. If Claude estimates 5%, market estimates 27%, final TP uses 16%.

Motivation: AIA Forecaster paper found LLMs' independent forecasts on liquid markets lose to market consensus; ensembled forecasts beat the market. The 50/50 here is a simplified version.

#### Mechanism 2: Three-Tier Edge Thresholds

| Scan Range | Report Header Marker | Edge Required |
|---|---|---|
| Standard | `# Standard Scan Result` | ≥ 8pp |
| Medium | `# 📊 Medium Scan Result` | ≥ 12pp |
| Wide | `# ⚠️ Wide Scan Result` | ≥ 15pp |

The wider the range, the higher execution cost (wider spread, thinner depth), so larger edge needed to clear margin. Claude is instructed to read the report header to choose the threshold.

#### Mechanism 3: "No Recommendation" is Valid Output

Explicitly tell Claude: if candidates don't have sufficient edge, "no recommendation today" is a valid output. Avoid forced recommendations to fill quota.

### 8.2 Claude Output Format (Human-Readable Card)

```
> **Recommendation**: <full market name>
> **Slug**: <slug copied verbatim from input>
> **Direction**: Buy YES / Buy NO
> **Current price**: 27%
> **Raw estimate**: 5%
> **Calibrated estimate**: 16%   ← fill into Dashboard TP
> **Calibrated edge**: 11pp
> **Settlement date**: 2026-MM-DD
> **Confidence**: High / Medium
>
> **Why bet on this** (3-5 sentences):
> <core logic + authoritative source>
>
> **Biggest risk**: <one sentence>
```

---

## 9. Dashboard

Access: `http://localhost:5050`

### 9.1 Panel Structure

| Section | Content |
|---|---|
| Top metrics | Total P&L · Position count · Total invested · Monitor interval |
| Market scanner | Two tabs: [Keyword Scan] [Tag Scan]. Keyword tab has 17 quick-word chips + input + three-tier scan buttons. Tag tab has range selector + 22 tag chips grouped by Tier |
| Position table | Name · Direction · Entry price · Current price · Cost · Value · Size · P&L% · TP input · Save button · Reeval badge (conditional) |
| Reeval badge | Yellow pulsing badge appears when position hits 80% progress + ≥5 days to settlement. Click expands menu: Copy prompt / A uplift / B skip / C close |
| Trigger price display | Each position with TP shows T1/T2/T3 (green) and W1/W2/W3 (red) prices |
| Auto rules table | Lists all SL/TP rules (in sync with code) |
| Research prompt section | DISCOVERY_PROMPT joined with latest scan report + copy buttons |
| Event log | Most recent 30 rows from events table |
| Live log | Last 80 lines of bot.log, refreshes every 3s |

### 9.2 Partial Refresh Mechanism

Earlier version used full-page reload every 30s. This wiped:

- Mid-progress scan report ("scanning..." status broken mid-way)
- Half-typed TP input
- Page scroll position

Current version uses partial refresh:

| Mechanism | Implementation |
|---|---|
| 30s refresh | Calls GET `/api/snapshot` for position data; JS locates DOM rows by `data-asset` attribute, only updates `cur_price` / `value` / `pnl_pct` spans |
| Top metrics | Same call returns aggregate data, updates corresponding ids |
| Position changes | Detect position count change (new buy / full exit) → trigger one full-page reload as fallback |
| Scan polling | After clicking scan, record `startTs`, poll `/api/scan_report` every 2s, only show new report when `mtime > startTs`; max 60s timeout |

---

## 10. API Routes

All routes are in `dashboard.py`. Route catalog:

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Dashboard main page |
| `/api/control` | POST | Multi-action control endpoint |
| ` action=scan` | | Keyword scan (params: keyword, mode) |
| ` action=scan_tag` | | Tag scan (params: tag, mode) |
| ` action=check` | | Manually trigger position check |
| ` action=refresh` | | Manually refresh position data |
| `/api/scan_report` | GET | Latest scan report + file mtime |
| `/api/full_prompt` | GET | DISCOVERY_PROMPT + report joined into full prompt |
| `/api/snapshot` | GET | Position snapshot (for partial refresh) |
| `/api/logs` | GET | Last 80 lines of bot.log |
| `/api/record_position` | POST | Save position metadata + TP, with direction sanity check (`tp > entry_price`); optional `entry_reason` / `claude_raw_estimate` |
| `/api/update_tp` | POST | Update existing TP, with same sanity check |
| `/api/reeval_prompt` | GET | Build reeval prompt for token_id (all position info pre-filled) |
| `/api/mark_reeval` | POST | Mark reeval result. body: `{token_id, action: uplift\|skip\|close, new_tp?}`; uplift simultaneously updates `new_tp` |

---

## 11. Setup & Daily Use

### 11.1 Startup Commands

```bash
# Enter project + activate venv
cd ~/polymarket-semi-auto
source .venv/bin/activate

# Background start (won't stop when terminal closes)
nohup python3 main.py > output.log 2>&1 &

# Check if started successfully
sleep 4 && tail -10 bot.log
```

### 11.2 Stop

```bash
pkill -f "main.py"

# If port still occupied
lsof -ti:5050 | xargs kill -9
```

### 11.3 Status Check

```bash
# Recent logs
tail -50 ~/polymarket-semi-auto/bot.log

# Real-time tail
tail -f ~/polymarket-semi-auto/bot.log

# Process status
ps aux | grep main.py | grep -v grep
```

### 11.4 Daily Workflow

#### Morning check

1. Open Dashboard, look at overnight position changes
2. Check whether any auto-executed T/W events happened (events table)
3. Assess current P&L and risk

#### Find opportunities

1. In scan section pick a tag or enter keyword
2. Select range (standard / medium / wide), click scan button
3. Click "Copy for Claude" to get full prompt with scan report
4. Paste into Claude.ai Research mode, wait 5-15 minutes
5. Read Claude's recommendation card, decide whether to enter
6. Go to Polymarket website, manually place Limit order (as maker)
7. Back in Dashboard, fill TP for that position, save

#### Position maintenance

1. After major news, re-evaluate TP (re-run Claude or manual judgment)
2. Modify TP in dashboard, save → trigger prices recompute
3. System monitors per new TP

---

## 12. Design Trade-offs & Known Limits

### 12.1 Design Choices

| Choice | What was sacrificed | What was gained |
|---|---|---|
| No position-sizing math | Kelly criterion, dynamic position adjustment | Simple implementation, suits small-capital scenarios (fixed minimum order size) |
| Manual order placement | 24/7 automation | Human judgment guard, avoids buying wrong target |
| FAK sell, no maker rebate | 0.5-1.5pp possible rebate | 100% fill guarantee, avoids stop-loss missed due to unfilled rest order |
| No scan history persistence | Cross-time market tracking | Simple filesystem, last_scan.md keeps latest only |
| 50-market cap on order book check | Markets matching price/time/volume but ranked beyond 50 are missed | Avoids rate limiting (one CLOB API call per market) |

### 12.2 Known Limits

- **Human-in-the-loop dependency**: order placement and TP filling require human, no positions can open when no one is around
- **TP input errors lead to wrong triggers**: sanity check (`tp > entry_price`) added but logical errors can still slip in (e.g. filling 5pp gap will cause small_edge to exit after small profit)
- **API failures during VPN instability**: retry=3 in place but doesn't fully eliminate
- **Claude Research subscription quota** (Claude Max plan has monthly cap)
- **Small orders may partial-fill due to thin order books** (logged as WARNING but still returns True)
- **Polymarket maker rebates only apply to Finance category**. Geopolitics, entertainment, politics only save taker fee — marginal benefit smaller than expected

### 12.3 Bug Fix History

These are all production-environment lessons, recorded for future reference:

| Bug | Root Cause | Fix |
|---|---|---|
| NO position trigger price reversed | Code treated NO position as "shorting", used sign=-1 to make take-profit downward, stop-loss upward | Unified to "holding token's price up = profit", YES/NO same logic |
| `sell()` fake success | API rejection (insufficient balance etc.) returned `success=False` but code returned True regardless | Strict check `result.success` AND `makingAmount > 0` |
| `price=0.01` limit colliding with order book | GTC default with 0.01 was misread by code as a single property error | Switched to FAK + best_bid strict limit protection |
| Dashboard full-reload kills mid-scan state | 30s setInterval reload | Switched to `/api/snapshot` partial refresh |
| Scan needed 2 clicks to see results | Fixed 8s setTimeout to fetch report, decoupled from actual scan completion | `/api/scan_report` returns file mtime; frontend polls until `mtime > startTs` |
| `copyP()` copied stale prompt | `{{ prompt }}` template variable only set at first render | `/api/full_prompt` returns real-time joined; copyP changed to async fetch |
| `sol` substring killed 411 Iran markets | BLACKLIST_KEYWORDS substring match hit `sol` inside `resolution` | `\b...\b` regex word-boundary match + removed too-short keywords |
| `scan_by_tag tag=Iran` returned 0 | Polymarket Gamma API param is not `tag`, must use `tag_slug=iran` | Reverse-mapped label → slug from 1000 events, statically injected; API call uses slug |

---

*— End of Document —*
