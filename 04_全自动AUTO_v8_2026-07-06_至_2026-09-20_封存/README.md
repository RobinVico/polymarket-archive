# Polymarket AUTO

> **v8.5.5** — independent version line (forked from the semi-auto 7.x on 2026-07-12; no longer synced).

**Fully-automated Polymarket trading bot (standalone-account edition).** Zero-human loop: scheduled scan → GLM market selection → hard-coded routing → auto buy → position monitoring → scheduled + crash-triggered re-evaluation → auto exit.

> 🔒 **Private repository — contains a live trading strategy and drives a real-money account. Do not make public.**
> Forked 2026-07-06 from a private semi-automated project (then v7.4.3) as an **independent copy**, and rebuilt toward full automation.

📖 [中文说明 → README.zh.md](README.zh.md) · [技术报告(架构+策略)→ 技术报告.md](技术报告.md) · [运行规则(活文档)→ CLAUDE.md](CLAUDE.md)

---

## The automated loop

```
09:00 / 21:00 (local)
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Streaming "scan-one-feed-one", 4 lanes in parallel                  │
│  for each whitelist tag:  fresh re-scan → ≥5-candidate gate → GLM    │
│  (each tag gets the freshest order book at the moment it hits GLM)   │
└─────────────────────────────────────────────────────────────────────┘
    │  candidates written the instant each tag finishes
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Immediate execution (producer / consumer)                          │
│  a recommendation appears → buy it right away, others keep analyzing │
│  routing:  0.40 < price < 0.85 → REAL buy (¼-Kelly size)            │
│            otherwise            → PAPER test position                │
│  every buy is serialized + universe-gated + drift-checked            │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
  Position monitor (30s)  ──►  trailing / tiered stop-loss + take-profit
    │
    ▼
  Daily 15:00 sweep + crash-triggered re-eval  ──►  GLM decides
    │                                                hold / update_q / exit
    ▼
  Offline auto-execution (real money)
```

Everything runs unattended. The LLM layer is **Zhipu GLM** (two keys, split by role); Claude is a fallback only if GLM fails.

## Architecture at a glance

| | |
|---|---|
| **Entry** | `autobot.py` (deliberately *not* `main.py`) · port **5052** · SQLite `v4.db` |
| **Pipeline modules** (new, isolated) | `auto_scheduler` · `auto_discovery` · `auto_glm_agent` · `auto_trader` · `auto_daily_reeval` · `auto_dashboard` |
| **Inherited strategy** (synced from the semi-auto project, fork-patched) | `monitor` · `auto_reeval` · `executor` · `scanner` · `db` · `tags` |
| **Homepage** | `/` = auto monitoring dashboard (per-day digest, alerts, holdings, reeval log) |
| **LLM** | Zhipu GLM (`glm-5.2`, native `search_pro` web search + multi-round agentic search); Claude = GLM-outage fallback |

New code lives **only** in `modules/auto_*.py` so strategy updates can be one-way synced from the parent project with zero conflicts. Intentional edits to synced modules ("fork patches") are catalogued in `技术报告.md` §12.

## Key rules (all user-decided, hard-coded)

- **Universe iron law** — only trade markets that actually appeared in a whitelist-tag scan report (double gate: tag ∈ whitelist **and** slug present in that tag's report). Guards against hallucinated or injected markets.
- **Routing** — `0.40 < price < 0.85` → real buy, else paper. No other gate.
- **≥5-candidate gate** — a tag with fewer than 5 scanned candidates isn't sent to GLM (saves API).
- **Re-eval** — daily 15:00 full-position sweep (4-wide) + crash-triggered; no-metadata positions are never re-eval'd (they raise a red alert instead).
- **No caps** — no daily-USD or position-count limit (sizing is governed by the ¼-Kelly calculator: cluster cap + monthly drawdown budget, hard-bounded to [$1, $15]).
- Two Zhipu keys never mixed · tags are immutable · no loss circuit-breaker / no notifications / no watchdog by design.

## Account architecture

This account uses Polymarket's 2026 **deposit-wallet** model and **requires `POLY_SIGNATURE_TYPE=3` (POLY_1271)** — signature types 0/1/2 return `$0` balance and a `maker address not allowed` error. `py_clob_client_v2` **1.0.2** is vendored in the repo root (not pip-installed; do not downgrade to 1.0.0, which signs sig=3 orders incorrectly).

## Running

```bash
cp .env.example .env      # fill in credentials (see below)
bash restart.sh           # only sanctioned start/restart (kills LISTEN-only on :5052, runs autobot.py)
tail -f bot.log
```

Required in `.env`: `POLY_PRIVATE_KEY`, `POLY_FUNDER`, `POLY_SIGNATURE_TYPE=3`, `ZHIPUAI_API_KEY_DISCOVERY`, `ZHIPUAI_API_KEY_REEVAL`, `DASHBOARD_PASSWORD`, `FLASK_SECRET_KEY`. Full setup, tunable env vars, and operational rules are in **`CLAUDE.md`**; architecture and strategy details are in **`技术报告.md`**.

## Isolation

Zero relationship with the sibling projects `~/polymarket` (legacy account, port 5051) and `~/polymarket-semi-auto` (frozen) — separate `.env` / database / venv / git repo. The only permitted cross-link is one-way copying of strategy code/docs *into* this repo.
