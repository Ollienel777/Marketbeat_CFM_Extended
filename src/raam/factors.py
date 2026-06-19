import pandas as pd

from raam.config import RaamConfig


def compute_daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    return prices.pct_change(fill_method=None).dropna(how="all")


def compute_momentum(prices: pd.DataFrame, lookback: int) -> pd.Series:
    recent = prices.iloc[-1]
    past = prices.iloc[-(lookback + 1)]
    return recent / past - 1.0


def compute_volatility(returns: pd.DataFrame, window: int) -> pd.Series:
    return returns.tail(window).std(axis=0)


def compute_avg_correlation(returns: pd.DataFrame, window: int) -> pd.Series:
    corr = returns.tail(window).corr()
    return corr.apply(lambda c: (c.sum() - 1) / (len(c) - 1), axis=0)


def compute_atr(highs: pd.DataFrame, lows: pd.DataFrame, closes: pd.DataFrame, window: int) -> pd.Series:
    prev_close = closes.shift(1)
    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=0).groupby(level=0).max()

    atr = tr.rolling(window).mean()
    return atr.iloc[-1]


def compute_trend_signal(closes: pd.DataFrame, atr: pd.Series, high_window: int, low_window: int) -> pd.Series:
    rolling_high = closes.rolling(high_window).max().iloc[-1]
    rolling_low = closes.rolling(low_window).min().iloc[-1]
    cur = closes.iloc[-1]

    upper = rolling_high + atr
    lower = rolling_low - atr

    trend = pd.Series(0, index=closes.columns)
    trend[cur > upper] = 1
    trend[cur < lower] = -1
    return trend


def score_calc(meta: pd.DataFrame, prices: pd.DataFrame, highs: pd.DataFrame, lows: pd.DataFrame, cfg: RaamConfig) -> pd.DataFrame:
    if meta.empty:
        return meta.copy()

    tickers = meta["Ticker"].tolist()
    close_sub = prices[tickers]
    high_sub = highs[tickers]
    low_sub = lows[tickers]

    returns = compute_daily_returns(close_sub)
    if returns.empty:
        return meta.iloc[:0]

    try:
        M = compute_momentum(close_sub, cfg.mom_lookback)
        V = compute_volatility(returns, cfg.vol_window)
        C = compute_avg_correlation(returns, cfg.corr_window)
        ATR = compute_atr(high_sub, low_sub, close_sub, cfg.atr_window)
        T = compute_trend_signal(close_sub, ATR, cfg.trend_high_window, cfg.trend_low_window)
    except Exception:
        return meta.iloc[:0]

    rank_M = M.rank(ascending=False)
    rank_V = V.rank(ascending=True)
    rank_C = C.rank(ascending=True)
    rank_T = T.rank(ascending=False)

    score = (
        cfg.weight_momentum * rank_M
        + cfg.weight_volatility * rank_V
        + cfg.weight_correlation * rank_C
        + cfg.weight_trend * rank_T
    )

    factors = pd.DataFrame({
        "Ticker": tickers,
        "Momentum": M.values,
        "Volatility": V.values,
        "AvgCorr": C.values,
        "Trend": T.values,
        "Score": score.values,
    }).set_index("Ticker")

    return meta.set_index("Ticker").join(factors, how="inner").reset_index()
