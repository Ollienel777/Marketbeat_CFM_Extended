import dataclasses
import itertools
from datetime import datetime

import pandas as pd

from raam.backtest import LOOKBACK_BUFFER_DAYS, compute_metrics, get_benchmark_equity_curve, get_rebalance_dates, run_backtest_on_data
from raam.config import RaamConfig
from raam.data import download_all_data, load_ticker_list
from raam.history import DEFAULT_DB_PATH, record_backtest_run

# Default windows for the sweep: four non-overlapping periods spanning different
# regimes (calm bull, pre-COVID volatility, COVID crash/2022 bear, concentrated
# mega-cap rally), so no single parameter combination can win just by luck on one period.
DEFAULT_WINDOWS = [
    ("2015-01-01", "2018-01-01"),
    ("2018-01-01", "2020-01-01"),
    ("2020-01-01", "2022-01-01"),
    ("2022-01-01", "2024-01-01"),
]

# Concentration-related parameters: how many positions, how concentrated by sector,
# how concentrated by single stock. Kept separate from lookback windows/factor weights
# to keep the grid tractable -- those can be swept separately later.
DEFAULT_GRID = {
    "max_stocks": [10, 15, 20, 25],
    "max_sector_weight": [0.25, 0.40, 0.60],
    "max_stock_weight": [0.10, 0.15, 0.25],
}


def generate_param_grid(grid: dict | None = None) -> list[dict]:
    """Cartesian product of every value in `grid`, one dict per combination."""
    grid = grid or DEFAULT_GRID
    keys = list(grid.keys())
    return [dict(zip(keys, values)) for values in itertools.product(*[grid[k] for k in keys])]


def make_label(prefix: str, params: dict, start: str, end: str) -> str:
    param_str = "_".join(f"{k}{v}" for k, v in params.items())
    return f"{prefix}_{param_str}_{start}_{end}"


def run_sweep(
    ticker_path: str,
    windows: list[tuple[str, str]] | None = None,
    grid: list[dict] | None = None,
    base_cfg: RaamConfig | None = None,
    sharpe_trials: int = 5_000,
    budget: float = 1_000_000,
    benchmark: str = "SPY",
    label_prefix: str = "sweep",
    db_path: str = DEFAULT_DB_PATH,
    record: bool = True,
) -> pd.DataFrame:
    """Backtests every parameter combination in `grid` against every window in
    `windows`, recording each as a labeled backtest (reusing the same history DB and
    dashboard comparison view as any other `raam-backtest` run). Returns a DataFrame
    with one row per (combination, window) with that run's metrics.

    Price data is downloaded once per window and reused across all combinations in
    that window -- the grid only changes portfolio construction, not what data is
    needed, so there's no reason to re-download per combination.
    """
    windows = windows or DEFAULT_WINDOWS
    grid = grid if grid is not None else generate_param_grid()
    base_cfg = base_cfg or RaamConfig()
    tickers = load_ticker_list(ticker_path)

    rows = []
    for start, end in windows:
        fetch_start = (pd.Timestamp(start) - pd.Timedelta(days=LOOKBACK_BUFFER_DAYS)).strftime("%Y-%m-%d")
        close, high, low, vol, meta = download_all_data(tickers, fetch_start, end)
        if close.empty:
            continue

        rebalance_dates = get_rebalance_dates(close.index, start, end, "ME")
        benchmark_curve = get_benchmark_equity_curve(benchmark, start, end, budget)
        benchmark_metrics = compute_metrics(benchmark_curve) if not benchmark_curve.empty else {}

        for params in grid:
            cfg = dataclasses.replace(base_cfg, initial_budget_cad=budget, sharpe_trials=sharpe_trials, **params)
            result = run_backtest_on_data(close, high, low, vol, meta, cfg, rebalance_dates, cfg.fallback_usd_to_cad)
            equity_curve = result["equity_curve"]
            metrics = compute_metrics(equity_curve)

            backtest_id = None
            if record and not equity_curve.empty:
                total_fees = sum(r["fees_cad"] for r in result["rebalance_log"])
                backtest_id = record_backtest_run(
                    db_path=db_path,
                    run_at=datetime.now().isoformat(timespec="seconds"),
                    label=make_label(label_prefix, params, start, end),
                    tickers_path=ticker_path, start_date=start, end_date=end, budget_cad=budget,
                    freq="ME", benchmark_ticker=benchmark, total_fees_cad=total_fees,
                    strategy_metrics=metrics, benchmark_metrics=benchmark_metrics,
                    equity_curve=equity_curve, benchmark_curve=benchmark_curve,
                )

            rows.append({
                **params,
                "window_start": start, "window_end": end, "backtest_id": backtest_id,
                **{f"strategy_{k}": v for k, v in metrics.items()},
            })

    return pd.DataFrame(rows)


def summarize_sweep(results: pd.DataFrame, group_keys: tuple[str, ...] = ("max_stocks", "max_sector_weight", "max_stock_weight")) -> pd.DataFrame:
    """Aggregates per-window results into one row per parameter combination, averaged
    across windows, ranked by average Sharpe (the metric least likely to just reward
    whichever combination happened to suit one window's regime)."""
    if results.empty:
        return results

    group_keys = [k for k in group_keys if k in results.columns]
    agg = results.groupby(group_keys).agg(
        avg_sharpe=("strategy_sharpe", "mean"),
        avg_cagr=("strategy_cagr", "mean"),
        avg_max_drawdown=("strategy_max_drawdown", "mean"),
        n_windows=("strategy_sharpe", "count"),
    ).reset_index()

    return agg.sort_values("avg_sharpe", ascending=False)
