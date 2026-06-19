import pandas as pd

from raam.history import get_run_positions, get_run_scored_universe, list_runs


def compute_sector_weights(positions: pd.DataFrame) -> pd.Series:
    """Sums portfolio weight by sector, sorted descending. Empty input -> empty Series."""
    if positions.empty:
        return pd.Series(dtype=float)
    return positions.groupby("sector")["weight"].sum().sort_values(ascending=False)


def compute_factor_comparison(scored_universe: pd.DataFrame, selected_tickers: set[str]) -> pd.DataFrame:
    """Mean momentum/volatility/avg_corr for selected stocks vs. the full screened universe."""
    if scored_universe.empty:
        return pd.DataFrame()

    selected = scored_universe[scored_universe["ticker"].isin(selected_tickers)]

    return pd.DataFrame({
        "momentum_mean": [selected["momentum"].mean(), scored_universe["momentum"].mean()],
        "volatility_mean": [selected["volatility"].mean(), scored_universe["volatility"].mean()],
        "avg_corr_mean": [selected["avg_corr"].mean(), scored_universe["avg_corr"].mean()],
    }, index=["Selected", "Universe"])


def get_run_overview(db_path: str, run_id: int) -> dict:
    """Bundles everything one dashboard page needs for a given run."""
    positions = get_run_positions(db_path, run_id)
    scored_universe = get_run_scored_universe(db_path, run_id)
    selected_tickers = set(positions["ticker"])

    return {
        "positions": positions,
        "scored_universe": scored_universe,
        "sector_weights": compute_sector_weights(positions),
        "factor_comparison": compute_factor_comparison(scored_universe, selected_tickers),
    }


def get_latest_run_id(db_path: str) -> int | None:
    runs = list_runs(db_path)
    if runs.empty:
        return None
    return int(runs.iloc[-1]["run_id"])


def compute_weight_drift(history_by_run: pd.DataFrame) -> pd.DataFrame:
    """Pivots a multi-run ticker history (e.g. from get_ticker_history) into a
    run_at-indexed weight series, for plotting how a position's weight changed over time."""
    if history_by_run.empty:
        return pd.DataFrame()
    return history_by_run.pivot_table(index="run_at", values="weight", aggfunc="first")
