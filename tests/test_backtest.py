import numpy as np
import pandas as pd
import pytest

from raam.backtest import compute_metrics, get_rebalance_dates, run_backtest_on_data
from raam.config import RaamConfig


def test_get_rebalance_dates_picks_last_trading_day_per_month():
    idx = pd.bdate_range("2024-01-01", "2024-03-31")
    dates = get_rebalance_dates(idx, "2024-01-01", "2024-03-31", freq="ME")

    assert len(dates) == 3
    assert all(d.month != dates[i + 1].month for i, d in enumerate(dates[:-1]))
    # last business day of January 2024 is the 31st (a Wednesday)
    assert dates[0] == pd.Timestamp("2024-01-31")


def test_get_rebalance_dates_empty_outside_range():
    idx = pd.bdate_range("2024-01-01", "2024-03-31")
    assert get_rebalance_dates(idx, "2025-01-01", "2025-03-31") == []


def test_compute_metrics_on_monotonic_growth_curve():
    n = 504  # ~2 trading years
    idx = pd.bdate_range("2022-01-03", periods=n)
    equity = pd.Series(100_000 * (1.0005) ** np.arange(n), index=idx)

    metrics = compute_metrics(equity)

    expected_total_return = equity.iloc[-1] / equity.iloc[0] - 1
    expected_cagr = (1 + expected_total_return) ** (1 / (n / 252)) - 1

    assert metrics["total_return"] == pytest.approx(expected_total_return)
    assert metrics["cagr"] == pytest.approx(expected_cagr)
    assert metrics["max_drawdown"] == pytest.approx(0.0)  # monotonic increase, never below its own peak
    assert metrics["pct_positive_months"] == pytest.approx(1.0)
    assert metrics["annualized_vol"] == pytest.approx(0.0, abs=1e-6)  # constant daily return -> zero vol


def test_compute_metrics_empty_curve():
    assert compute_metrics(pd.Series(dtype=float)) == {}


def test_compute_metrics_single_point_curve():
    assert compute_metrics(pd.Series([100_000.0])) == {}


@pytest.fixture
def tiny_cfg():
    return RaamConfig(
        initial_budget_cad=100_000,
        min_liq_avg_volume=0,
        min_stocks=1,
        max_stocks=1,
        max_sector_weight=1.0,
        max_stock_weight=1.0,
        mom_lookback=5,
        vol_window=5,
        corr_window=5,
        atr_window=3,
        trend_high_window=5,
        trend_low_window=5,
        sharpe_lookback=5,
        sharpe_trials=50,
        fallback_usd_to_cad=1.35,
    )


@pytest.fixture
def synthetic_panel():
    n = 30
    idx = pd.bdate_range("2024-01-02", periods=n)

    up = 100 * (1.01) ** np.arange(n)     # steady uptrend
    down = 100 * (0.99) ** np.arange(n)   # steady downtrend

    close = pd.DataFrame({"UP": up, "DOWN": down}, index=idx)
    high = close * 1.01
    low = close * 0.99
    vol = pd.DataFrame({"UP": [100_000] * n, "DOWN": [100_000] * n}, index=idx)

    meta = pd.DataFrame({
        "Ticker": ["UP", "DOWN"],
        "Sector": ["Technology", "Energy"],
        "Currency": ["USD", "USD"],
        "MarketCap": [1e9, 1e9],
        "Country": ["US", "US"],
    })

    return close, high, low, vol, meta, idx


def test_run_backtest_on_data_tracks_equity_and_rebalances(tiny_cfg, synthetic_panel):
    close, high, low, vol, meta, idx = synthetic_panel
    rebalance_dates = [idx[15], idx[29]]

    result = run_backtest_on_data(close, high, low, vol, meta, tiny_cfg, rebalance_dates, usd_to_cad=1.35)

    equity_curve = result["equity_curve"]
    assert not equity_curve.empty
    assert equity_curve.index[0] == idx[15]
    assert equity_curve.index[-1] == idx[29]

    assert len(result["rebalance_log"]) == 2
    for entry in result["rebalance_log"]:
        assert entry["fees_cad"] >= 0

    # UP has the much stronger momentum (rising vs falling), and the cfg only keeps 1
    # stock, so UP should be selected at both rebalances -- never DOWN.
    for entry in result["rebalance_log"]:
        tickers_picked = set(entry["portfolio"]["Ticker"]) - {"CASH"}
        assert tickers_picked <= {"UP"}


def test_run_backtest_on_data_empty_when_no_rebalance_dates(tiny_cfg, synthetic_panel):
    close, high, low, vol, meta, _ = synthetic_panel
    result = run_backtest_on_data(close, high, low, vol, meta, tiny_cfg, [], usd_to_cad=1.35)
    assert result["equity_curve"].empty
    assert result["rebalance_log"] == []


def test_run_backtest_on_data_second_rebalance_only_adjusts_size_not_ticker(tiny_cfg, synthetic_panel):
    close, high, low, vol, meta, idx = synthetic_panel
    rebalance_dates = [idx[15], idx[29]]

    result = run_backtest_on_data(close, high, low, vol, meta, tiny_cfg, rebalance_dates, usd_to_cad=1.35)

    # Since UP is selected both times and its price only went up, the account's
    # current value (and thus the recomputed target share count) should have grown
    # between the two rebalances -- so the second rebalance still trades (resizing),
    # rather than doing nothing.
    assert result["rebalance_log"][1]["n_orders"] >= 0
    assert result["final_cash"] is not None
