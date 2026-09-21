<div align="right"><b>English</b> | <a href="README.zh.md">中文</a></div>

# History — every version and iteration (2026-04 → 2026-09)

Complete archive of the project's 5.5-month evolution. **Start with the [Project Summary Report — bilingual HTML, English default](00_final-reports/Project-Summary-Report_2026-09-20_bilingual.html)** (or the [English PDF](00_final-reports/Project-Summary-Report_2026-09-20_EN.pdf)): full timeline, final results of the three-account experiment, incident log, lessons learned and a restart-improvement list.

## Folders (chronological)

| Folder | Stage | Period | What's inside |
|---|---|---|---|
| `00_final-reports/` | — | 2026-09-20 | Project summary report (bilingual HTML with EN/中文 toggle, EN & ZH PDF/Word) + final three-account report (Chinese) |
| `01_prehistory-v1_browser-automation_2026-04/` | v1 | Apr 8–16 | The very first attempt: browser automation driving Gemini Deep Research for market discovery (includes an Apr-15 full backup and debug screenshots) |
| `02_v3_semi-auto-initial_2026-04-27_frozen/` | v3 | Apr 27 (frozen) | The prototype: human places orders, Claude does analysis, bot runs tiered take-profit / stop-loss |
| `03_semi-auto-main_v4-v7_2026-05_to_07/` | v4→v7.5.4 | May 9 – Jul 24 | The main battleground: decision engine, re-evaluation system and dashboard matured here. **Earlier generations (v4, v5, v5.6–5.9) are archived inside its `past/` directory.** Includes the trading database and two v7.5.4 slide decks |
| `05_misc_early-docs_research-PDFs_memory/` | evidence | Apr–Sep | v1/v2/v3 technical docs, May-2026 AI research PDFs, curated project memory notes |
| `06_side-project_weather-bot/` | side line | since Jul 12 | Polymarket daily-max-temperature arbitrage (after sunset the temperature only falls — buy the 0.90–0.995 bucket); independent wallet and strategy |

*(There is no `04` here — the final AUTO v8 system is the repo's top-level [`latest_AUTO-v8.5.5_three-account-system/`](../latest_AUTO-v8.5.5_three-account-system/).)*

## Final results (asset-truth basis: current assets − net deposits)

| Account / strategy | Net deposit | Assets at seal | P&L |
|---|---:|---:|---:|
| Main — full auto strategy (Kelly sizing + 3-tier SL + TP + LLM re-eval) | $99.66 | $90.61 | **−9.1%** |
| Bench — baseline (take every rec; only rule: sell at −30%) | $90.47 | $41.81 | **−53.8%** |
| Shadow — low-price hold (only ≤0.40; −60% SL; hold to resolution) | $50.00 | $22.16 | **−55.7%** |
| **Total** | **$240.13** | **$154.58** | **−35.6%** |

**Key findings:** ① same AI recommendations, wildly different outcomes — **the money saved came from exit discipline, not from market selection**; ② the LLM's raw prediction accuracy was 56.8% overall (83/146) but only 11/45 below 40¢ — **LLMs systematically overrate low-price long shots**; ③ at $2–5 position sizes, trading friction (rounding, spread, unsellable dust) eats any edge.

## Version line at a glance

v1 (Apr 8–16, browser automation + Gemini) → v3 (Apr 27, semi-auto frozen) → v4.1 (May 9) → v5.1 decision-engine rewrite (May 19–24) → v6.0 auto re-evaluation (Jun 18–19) → v7.0/7.1 exit redesign + paper trading (Jun 22) → v7.4–7.5.4 semi-auto final (Jul 6–13) → **AUTO fork (Jul 6) → full automation live (Jul 8) → v8.0.0 (Jul 12) → strategy iteration burst (mid-late Jul) → Bench + Shadow three-account experiment (Jul 23–24) → outage (Aug 12–27) → v8.5.5 paid APIs stopped (Sep 1) → sealed (Sep 20)**.

Most in-folder documents (reports, PPTs, CLAUDE.md rule history) are historical artifacts in Chinese; the summary report above carries the full story in English.
