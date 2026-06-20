import numpy as np
import pandas as pd
import pytest

from raam.factors import (
    compute_atr,
    compute_avg_correlation,
    compute_daily_returns,
    compute_momentum,
    compute_trend_signal,
    compute_volatility,
)


@pytest.fixture
def prices():
    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    rng = np.random.default_rng(0)

    up = 100 * (1 + 0.001) ** np.arange(n)  # steady uptrend
    down = 100 * (1 - 0.001) ** np.arange(n)  # steady downtrend
    flat = 100 + rng.normal(0, 0.5, n)  # noisy flat

    return pd.DataFrame({"UP": up, "DOWN": down, "FLAT": flat}, index=idx)


def test_compute_daily_returns_drops_first_row(prices):
    returns = compute_daily_returns(prices)
    assert len(returns) == len(prices) - 1
    assert not returns.isna().any().any()


def test_compute_momentum_ranks_uptrend_above_downtrend(prices):
    mom = compute_momentum(prices, lookback=84)
    assert mom["UP"] > mom["FLAT"] > mom["DOWN"]


def test_compute_volatility_is_higher_for_noisy_series(prices):
    returns = compute_daily_returns(prices)
    vol = compute_volatility(returns, window=60)
    assert vol["FLAT"] > vol["UP"]
    assert vol["FLAT"] > vol["DOWN"]


def test_compute_volatility_weights_recent_observations_more_than_old_ones():
    # Two return series with the *same* values, just reordered: one had a volatile
    # patch early (now calm), the other had a volatile patch recently. A flat rolling
    # std treats both identically (order doesn't matter to it) -- EWMA should not,
    # since it's specifically meant to react to recent volatility shifts.
    n = 15
    idx = pd.date_range("2024-01-01", periods=2 * n, freq="B")
    high_vol = np.tile([0.05, -0.05], n // 2 + 1)[:n]
    low_vol = np.tile([0.005, -0.005], n // 2 + 1)[:n]

    recent_calm = pd.DataFrame({"X": np.concatenate([high_vol, low_vol])}, index=idx)
    recent_volatile = pd.DataFrame({"X": np.concatenate([low_vol, high_vol])}, index=idx)

    flat_std_calm = recent_calm.tail(2 * n).std()
    flat_std_volatile = recent_volatile.tail(2 * n).std()
    assert flat_std_calm["X"] == pytest.approx(flat_std_volatile["X"])  # order-blind, as expected

    ewma_calm = compute_volatility(recent_calm, window=n, smooth_window=1)
    ewma_volatile = compute_volatility(recent_volatile, window=n, smooth_window=1)
    assert ewma_volatile["X"] > ewma_calm["X"]  # EWMA correctly weights the recent spike more


def test_compute_avg_correlation_shape(prices):
    returns = compute_daily_returns(prices)
    corr = compute_avg_correlation(returns, window=63)
    assert set(corr.index) == {"UP", "DOWN", "FLAT"}
    assert (corr <= 1.0).all() and (corr >= -1.0).all()


def test_compute_atr_nonnegative(prices):
    highs = prices * 1.01
    lows = prices * 0.99
    atr = compute_atr(highs, lows, prices, window=42)
    assert (atr >= 0).all()


def test_compute_trend_signal_flags_breakout_and_breakdown(prices):
    # A sharp final move should register as a breakout/breakdown relative to
    # the *prior* rolling range (today's close is excluded from that range).
    breakout_prices = prices.copy()
    breakout_prices.iloc[-1, breakout_prices.columns.get_loc("UP")] *= 1.10
    breakout_prices.iloc[-1, breakout_prices.columns.get_loc("DOWN")] *= 0.90

    highs = breakout_prices * 1.01
    lows = breakout_prices * 0.99
    atr = compute_atr(highs, lows, breakout_prices, window=42)
    trend = compute_trend_signal(breakout_prices, atr, high_window=63, low_window=105)

    assert trend["UP"] == 1
    assert trend["DOWN"] == -1
    assert trend["FLAT"] == 0


def test_compute_trend_signal_is_neutral_without_a_breakout(prices):
    highs = prices * 1.01
    lows = prices * 0.99
    atr = compute_atr(highs, lows, prices, window=42)
    trend = compute_trend_signal(prices, atr, high_window=63, low_window=105)
    assert (trend == 0).all()
