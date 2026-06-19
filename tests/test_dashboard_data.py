import pandas as pd
import pytest

from raam.dashboard_data import compute_factor_comparison, compute_sector_weights, compute_weight_drift


def test_compute_sector_weights_sums_and_sorts():
    positions = pd.DataFrame({
        "sector": ["Tech", "Tech", "Energy", "Healthcare"],
        "weight": [0.2, 0.1, 0.25, 0.45],
    })
    weights = compute_sector_weights(positions)

    assert list(weights.index) == ["Healthcare", "Tech", "Energy"]
    assert weights["Tech"] == pytest.approx(0.3)


def test_compute_sector_weights_empty_input():
    assert compute_sector_weights(pd.DataFrame()).empty


def test_compute_factor_comparison_separates_selected_from_universe():
    scored_universe = pd.DataFrame({
        "ticker": ["AAPL", "KO", "XOM"],
        "momentum": [0.12, 0.05, -0.03],
        "volatility": [0.02, 0.01, 0.03],
        "avg_corr": [0.3, 0.2, 0.1],
    })
    comparison = compute_factor_comparison(scored_universe, selected_tickers={"AAPL", "KO"})

    assert comparison.loc["Selected", "momentum_mean"] == (0.12 + 0.05) / 2
    assert comparison.loc["Universe", "momentum_mean"] == (0.12 + 0.05 - 0.03) / 3


def test_compute_factor_comparison_empty_universe():
    assert compute_factor_comparison(pd.DataFrame(), selected_tickers=set()).empty


def test_compute_weight_drift_pivots_by_run():
    history = pd.DataFrame({
        "run_at": ["2026-06-01T00:00:00", "2026-06-08T00:00:00"],
        "weight": [0.10, 0.15],
    })
    drift = compute_weight_drift(history)

    assert list(drift.index) == ["2026-06-01T00:00:00", "2026-06-08T00:00:00"]
    assert drift.loc["2026-06-08T00:00:00", "weight"] == 0.15


def test_compute_weight_drift_empty_input():
    assert compute_weight_drift(pd.DataFrame()).empty
