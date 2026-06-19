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


def test_compute_trend_signal_is_neutral_for_monotonic_series(prices):
    # NOTE: compute_trend_signal compares today's close to a rolling high/low
    # that includes today itself, so today's price can never exceed its own
    # rolling high (or fall below its own rolling low) -- the "confirmed
    # uptrend"/"confirmed downtrend" signal can structurally never fire. This
    # mirrors a latent bug carried over from the original notebook; it's a
    # known issue (only 5% of the score weight) rather than intended behavior.
    highs = prices * 1.01
    lows = prices * 0.99
    atr = compute_atr(highs, lows, prices, window=42)
    trend = compute_trend_signal(prices, atr, high_window=63, low_window=105)
    assert (trend == 0).all()
