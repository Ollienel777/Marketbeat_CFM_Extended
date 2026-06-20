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

By default each scheduled run only does the recompute step: `raam` rebuilds the target
portfolio from current data and records it to `raam_history.db`. It does **not** place
trades automatically -- pass `-SyncPaperAccount:$true` to also run `raam-trade --execute`
each week.

That's off by default on purpose: IBKR's API needs TWS or IB Gateway already running and
logged into your paper account at the scheduled time (it's a local desktop app, not a pure
cloud API like Alpaca's), and IBKR's 2FA can block a fully unattended login even if the app
is open. Until that's set up reliably (IB Gateway's auto-restart + saved-login settings, or
a headless-login tool like IBC), the practical workflow is: let the scheduled task recompute
the portfolio automatically every week, and run `raam-trade --execute` yourself whenever IB
Gateway happens to be open.

Output is appended to `logs\raam_run.log` after every run. Re-run `register_schedule.ps1`
(e.g. to change the day/time or toggle `-SyncPaperAccount`) and it updates the existing task
instead of duplicating it.

## Paper trading (Interactive Brokers)

`raam-trade` syncs an IBKR paper-trading account to a recorded run's target portfolio.
**Alpaca was tried first but doesn't support Canadian residents** (even for paper trading),
so this uses Interactive Brokers instead, which does. Only US-listed equities are routed
through this; non-US-equity picks (Canadian `.TO` tickers, futures like `GC=F`, crypto pairs
like `BTC-USD`) are reported separately and skipped, not traded.

```bash
pip install -e ".[broker]"
```

Unlike a pure cloud API, IBKR's API connects to a local desktop app:

1. Open an IBKR account and install **Trader Workstation (TWS)** or the lighter **IB
   Gateway**.
2. Log into TWS/IB Gateway with your **paper-trading** credentials (paper account IDs start
   with `D`; `get_trading_client()` refuses to trade if it doesn't see one, as a safety
   check against accidentally hitting a live account).
3. Enable API access: File/Configure > Settings > API > Enable ActiveX and Socket Clients.
4. Note the socket port shown there -- TWS paper trading defaults to `7497`, IB Gateway
   paper trading defaults to `4002`.

Connection settings can be overridden via env vars if needed: `IBKR_HOST` (default
`127.0.0.1`), `IBKR_PORT` (default `7497`), `IBKR_CLIENT_ID` (default `1`).

```bash
raam-trade                  # dry run against the latest recorded run -- shows orders, submits nothing
raam-trade --run-id 3       # dry run against a specific run
raam-trade --execute        # actually places the buy/sell orders on the paper account
```

It diffs the target portfolio's share counts against your current IBKR paper positions and
only submits the delta (so re-running it after a partial fill or a new weekly run just trues
up the account rather than re-buying everything from scratch). IBKR's API also rejects
fractional-share orders, so target share counts are rounded down to whole shares before
they're shown or submitted (an order that rounds to 0 shares is skipped, not sent as a
zero-quantity order).

## Tracking P&L

Every time `raam-trade` connects, it snapshots your real IBKR paper account's net
liquidation value, cash, and unrealized/realized P&L into `raam_history.db` (pass
`--no-snapshot` to skip this). This is the actual account's equity, not a theoretical
mark-to-market of the strategy's picks, so it reflects real fills and price moves.

```bash
raam-history pnl     # prints every recorded snapshot, plus net change since the first one
```

The dashboard also charts this as an equity curve (see below).

## Dashboard

A read-only Streamlit dashboard over the history DB: run picker, portfolio table, sector
allocation chart, risk/return scatter (selected vs. screened universe), a rebalance preview,
an account equity/P&L curve, and per-ticker weight history across runs. It never submits
trades — that stays in `raam-trade`, run deliberately from a terminal.

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
- `src/raam/history.py` — SQLite persistence for past runs, their positions, and account equity snapshots.
- `src/raam/history_cli.py` — `raam-history` command-line entrypoint.
- `src/raam/broker.py` — IBKR paper-trading client, tradability rules, rebalance math.
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
