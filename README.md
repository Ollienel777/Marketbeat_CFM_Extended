# RAAM — Ranked Asset Allocation Model

A rules-based, multi-factor portfolio strategy. Ranks a candidate stock universe on
momentum, volatility, correlation, and trend, builds a sector-capped, Sharpe-optimized
portfolio, and applies an absolute-momentum sell-to-cash overlay.

This started as a course assignment (`Team_17_Assignment.ipynb`, `Team_XX_Assignment.ipynb`)
and is being rebuilt here as a reusable, testable package.

## Install

```bash
pip install -e ".[dev]"
```

## Run

```bash
raam --tickers Tickers_file.csv --start 2024-10-01 --end 2025-11-21 --budget 1000000 --out results
```

Writes a `portfolio_<timestamp>.csv` (selected tickers, shares, weights, value) and a
`scored_universe_<timestamp>.csv` (every screened ticker with its factor scores) to `--out`,
and records the run (metadata + positions) to a SQLite history DB (default `raam_history.db`).
Pass `--no-history` to skip recording, or `--history-db <path>` to use a different DB file.

## History

Inspect recorded runs with the `raam-history` command:

```bash
raam-history list                # every recorded run
raam-history show <run_id>       # positions from one run
raam-history ticker AAPL         # how a ticker's position changed across all runs
```

## Scheduling

`raam` is a one-shot CLI; recurring runs are driven by the OS scheduler, not a background
process. On Windows, register a weekly job with:

```powershell
.\scripts\register_schedule.ps1 -TickersPath "Tickers_file.csv"
```

This runs `raam` every Monday at 07:00, logging output to `logs\raam_run.log` and appending
to `raam_history.db`. Re-run the script (e.g. to change the day/time) and it updates the
existing task instead of duplicating it.

## Paper trading (Alpaca)

`raam-trade` syncs an Alpaca paper-trading account to a recorded run's target portfolio.
Alpaca's paper trading only supports US-listed equities, so non-US-equity picks (Canadian
`.TO` tickers, futures like `GC=F`, crypto pairs like `BTC-USD`) are reported separately
and skipped, not traded.

```bash
pip install -e ".[broker]"
```

Set your Alpaca **paper-trading** API keys (not live keys) as environment variables:

```bash
export ALPACA_API_KEY=...
export ALPACA_SECRET_KEY=...
```

```bash
raam-trade                  # dry run against the latest recorded run -- shows orders, submits nothing
raam-trade --run-id 3       # dry run against a specific run
raam-trade --execute        # actually places the buy/sell orders on the paper account
```

It diffs the target portfolio's share counts against your current Alpaca paper positions
and only submits the delta (so re-running it after a partial fill or a new weekly run just
trues up the account rather than re-buying everything from scratch).

## Dashboard

A read-only Streamlit dashboard over the history DB: run picker, portfolio table, sector
allocation chart, risk/return scatter (selected vs. screened universe), a rebalance preview,
and per-ticker weight history across runs. It never submits trades — that stays in
`raam-trade`, run deliberately from a terminal.

```bash
pip install -e ".[dashboard]"
raam-dashboard
```

## Test

```bash
pytest
```

## Layout

- `src/raam/config.py` — strategy parameters (lookback windows, caps, weights).
- `src/raam/data.py` — ticker loading, price/metadata download (yfinance), universe filtering.
- `src/raam/factors.py` — momentum, volatility, correlation, ATR, trend, and the weighted score.
- `src/raam/portfolio.py` — sector-capped selection, Sharpe optimization, sell-to-cash, sizing.
- `src/raam/strategy.py` — orchestrates the full pipeline, including fee-adjusted final sizing.
- `src/raam/cli.py` — `raam` command-line entrypoint.
- `src/raam/history.py` — SQLite persistence for past runs and their positions.
- `src/raam/history_cli.py` — `raam-history` command-line entrypoint.
- `src/raam/broker.py` — Alpaca paper-trading client, tradability rules, rebalance math.
- `src/raam/trade_cli.py` — `raam-trade` command-line entrypoint.
- `src/raam/dashboard_data.py` — pure helper functions for the dashboard (sector weights, factor stats, weight drift).
- `src/raam/dashboard.py` — the Streamlit app.
- `src/raam/dashboard_cli.py` — `raam-dashboard` command-line entrypoint.
- `scripts/register_schedule.ps1` — registers a weekly Windows Task Scheduler job.

## Bugs fixed vs. the original notebook

- `select_top_stocks` sized each candidate's sector weight against the number of stocks
  chosen *so far* instead of the target portfolio size, so the very first pick always
  "weighed" 100% and was rejected — the 40% sector cap was never actually enforced; it
  silently fell back to picking the top-N stocks by score every run. Fixed by weighting
  candidates against `max_stocks`.
- `compute_trend_signal` compared today's close against a rolling high/low window that
  included today itself, so the breakout/breakdown signal could structurally never fire.
  Fixed with `shift(1)` so the comparison is against the prior range.
