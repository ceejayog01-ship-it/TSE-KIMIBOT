# TSE + KimiBot Executor (51 BEST) — fixed build

Scans five pairs for the 51 "BEST" research strategies on the last completed **M30** bar, sends every
signal to **Telegram**, and (optionally) places the trades on MT5 through a headless bridge that lives only
for the length of one GitHub Actions run. No VPS, no always-on process, no `.env` file.

**Pairs scanned:** XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD — every 30 minutes, every day, all hours (no session or weekday filter).

## How a run works (every 30 minutes, every day)

1. **Gate** (`session_gate.py`): always active now; it only exists so the workflow keeps its structure.
2. **Start the MT5 bridge** (Docker image `liberatti/mt5bridge`, bound to localhost) and **wait until it is really connected to your broker**.
3. **Scan** (`scan_once.py`): pull the last 400 M30 candles per pair from the bridge, drop the forming bar, evaluate the 51 strategies, send Telegram messages.
4. **Execute / manage** (`mt5_execute.py`): close Design A trades after 24h, tighten stops hourly, open new trades for the pairs allowed to auto-trade.
5. **Save state** (`state/`: ledger, cooldowns, signal and outcome logs) back to the repo, then stop the bridge.

### Two designs per signal (opened side by side)
| | SL | TP | Exit |
|---|---|---|---|
| **A – Research** | 2 × ATR(14, M30) | none | closed after 48 M30 bars (~24h) |
| **B – Hybrid** | 2 × ATR(14, M30) | the strategy's research net return, converted to a price distance (net × entry price) | broker TP |

Both designs: every hour the stop is tightened by +1 ATR(M30) in the trade direction, but never closer to the live price than the broker allows, and never loosened.

## What was fixed compared with the uploaded zip

| # | Problem in the uploaded version | Fix |
|---|---|---|
| 1 | The executor called `/order/send`, `/position/modify`, `/close_position`. None of these is in the bridge's documented API, so orders, stop changes and closes would all fail. | Uses only documented endpoints: `/order/open`, `/order/modify`, `/order/close`, `/positions_get`, `/history_deals_get`, `/symbol_info*`. |
| 2 | The workflow waited a fixed `sleep 15`. The terminal needs minutes to log in, so the scan found no data and did nothing. | Polls until the terminal reports *connected* and the account is loaded (up to 6 minutes). |
| 3 | Candles requested with `timeframe: 30`; the bridge documents names like `M30`. Prices were also requested without your broker's symbol suffix. | Sends `M30` and appends `KB_SYMBOL_SUFFIX`. |
| 4 | The "+1 ATR hourly" rule jumped the stop from entry − 2 ATR to **entry + 1 ATR** in one step, above the live price. | Stop moves up by exactly 1 ATR each hour, clamped to a valid distance below (buys) / above (sells) the live price; skipped and retried if price is too close. |
| 5 | Design B's take-profit used the research *return* (e.g. 0.0013) as a price distance: fine-ish for EURUSD, nonsense for gold (≈ $0.0013) or USDJPY. | TP distance = research net × entry price. |
| 6 | Design B could never trade: the code allowed only one TSE position per symbol, and A always filled first. | One position per symbol **and design**. |
| 7 | Execution mode could be changed by a dispatch input or repository variable. | `DRY_RUN: 'false'` is hard-coded in the workflow; no input or variable feeds it. Executor fails closed unless MT5 reports `trade_mode` 0 (DEMO) or 2 (REAL). |
| 8 | The cooldown file was read but never written, so the same signal repeated every run. | Cooldown is recorded when a signal is sent. |
| 9 | The scan never sent Telegram signals (only the executor sent "EXECUTED" messages). | Every signal goes to Telegram, including pairs that are not auto-traded. |
| 10 | Cron ran every 15 minutes, 24/7, and started the terminal each time. | Every 30 minutes, every day, all hours (as requested). |
| 11 | State was pushed with `git push || true` and no write permission, plus no protection against overlapping runs. | `permissions: contents: write`, one run at a time, pull-rebase with retries. |
| 12 | Silent failures: a dead bridge still produced a green run. | Bridge errors on positions / symbol info / sizing now raise and fail the run; a scan where an auto-traded pair (EURUSD) could not be fetched exits red (the executor still runs afterwards); a failed state push exits red. Red runs send a Telegram alert. |
| 13 | Test rows (`STRAT_TEST`) were committed in the state logs; unpinned image; bridge port open on all interfaces. | Clean state; port bound to localhost; pin the image digest after your first successful test. |

## Setup (GitHub → Settings → Secrets and variables → Actions)

**Secrets:** `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_API_KEY` (any long random string), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

**Variables (all optional):**

| Variable | Default | Meaning |
|---|---|---|
| `KB_PAIRS` | all five | pairs scanned and sent to Telegram |
| `KB_EXEC_PAIRS` | `EURUSD` | pairs whose signals are traded. See the caution below. |
| `KB_SYMBOL_SUFFIX` | none | broker suffix, e.g. `.m` |
| `KB_RISK_PERCENT` | `1.0` | % of equity risked per trade (each design is its own trade) |
| `KB_LOT_SIZE` | empty | fixed lots; overrides risk sizing |
| `KB_MAX_VOLUME` | `0.10` | hard cap on lots |
| `KB_MAX_OPEN` | `4` | max simultaneous TSE positions |
| `KB_DESIGNS` | `A,B` | which designs to emit |
| `KB_DEBUG_LOGS` | off | `true` prints bridge logs on failure (they can contain your account number; keep off in a public repo) |

The workflow enables broker-side order requests (`DRY_RUN=false`) on every run. A hard account-mode guard checks the MT5 `account_info.trade_mode` field and permits execution only when it equals `0` (DEMO) or `2` (REAL). Missing, unknown and contest (`1`) modes are rejected. **With a REAL account, orders are real money.** The workflow has no manual dry-run toggle. Verify that the bridge returns the documented MT5 `trade_mode` field before relying on the guard.

## Read this before trading more than EURUSD

* The 51 strategies and the frozen volatility/trend thresholds were researched on **EURUSD only**. The other four pairs are scanned and reported, but **not auto-traded** until you add them to `KB_EXEC_PAIRS`.
* Their messages are marked *"Thresholds are the EURUSD ones"*. To calibrate a pair's thresholds from TRAIN-period M30 data: `python calibrate_thresholds.py --csv GBPUSD_M30.csv --pair GBPUSD --from 2023-01-01 --to 2023-12-31 --write`. This fixes the volatility/trend states only; it does **not** show the strategies have an edge on that pair.
* The strategies' direction/strength/persistence conditions use a **momentum proxy** (stated in `strategy_eval.py`), not the research alpha engine. On sampled EURUSD London/NY bars from 2020–2022, at least one strategy agreed on most bars, so expect signals almost every scan. Compare live outcomes (`python analyze_logs.py`) with research before scaling up.

## Known limits
* The execution path and account-mode guard have not been verified against your broker's actual MT5 bridge instance. Confirm the account-info response and test with a demo account; do not treat a successful workflow run as proof of strategy profitability.
* `/order/modify` and `/order/close` payloads (`ticket`, `sl`, `tp`) are not fully documented; the executor confirms every stop change by re-reading the position and alerts if it can't.
* Stops are managed when the executor runs (every 30 minutes), so the "hourly" tighten and the 24h close happen at the next run after the time is reached; weekend holds are handled on Monday.
* Each run logs into the broker from a fresh GitHub IP; some brokers may throttle this.
* State is committed to the repo. In a public repo, your tickets, entry levels and outcomes are public.

## Files
`scan_once.py` · `mt5_execute.py` · `session_gate.py` · `calibrate_thresholds.py` · `analyze_logs.py` · `config.py` · `states/` (market states, strategy evaluator, per-pair thresholds) · `data/` (51 strategies, edges, `pair_thresholds.json`) · `utils/` · `.github/workflows/scan.yml` · `state/` (ledger, cooldowns, logs)
