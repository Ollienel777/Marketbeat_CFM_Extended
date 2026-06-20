import dataclasses

import numpy as np
import pandas as pd

from raam.broker import compute_rebalance_orders
from raam.config import RaamConfig
from raam.data import download_all_data, load_ticker_list
from raam.strategy import apply_trading_fees, compute_portfolio

TRADING_DAYS_PER_YEAR = 252

# Calendar-day buffer fetched before the requested start date, so the first rebalance
# already has enough history for the longest lookback window (Sharpe lookback, 126
# trading days ~= 183 calendar days). Padded generously to also cover holidays/weekends.
LOOKBACK_BUFFER_DAYS = 220


def get_rebalance_dates(price_index: pd.DatetimeIndex, start: str, end: str, freq: str = "ME") -> list:
    """Picks the last trading day of each period (month-end by default) within [start, end]."""
    idx = price_index[(price_index >= pd.Timestamp(start)) & (price_index <= pd.Timestamp(end))]
    if idx.empty:
        return []
    return list(pd.Series(idx, index=idx).resample(freq).last().dropna())


def _price_on(close: pd.DataFrame, ticker: str, date) -> float | None:
    if ticker not in close.columns:
        return None
    series = close[ticker].loc[:date].dropna()
    return float(series.iloc[-1]) if not series.empty else None


def run_backtest_on_data(
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    vol: pd.DataFrame,
    meta: pd.DataFrame,
    cfg: RaamConfig,
    rebalance_dates: list,
    usd_to_cad: float,
) -> dict:
    """Walk-forward simulation core. Fully offline: takes already-downloaded price
    panels and never looks past whatever row it's currently processing, so this is
    safe to call directly in tests without any network access.

    At each rebalance date, re-runs the live strategy's own compute_portfolio/
    apply_trading_fees against data sliced up to that date only, diffs the resulting
    target shares against current holdings (reusing the same rebalance-order math
    raam-trade uses against a real broker), and marks the account to market daily.

    Returns a dict with: equity_curve (daily pd.Series), rebalance_log (list of dicts
    with date/portfolio/meta_scored/meta_sel/n_orders/fees_cad), final_holdings, final_cash.
    """
    if not rebalance_dates or close.empty:
        return {"equity_curve": pd.Series(dtype=float), "rebalance_log": [], "final_holdings": {}, "final_cash": cfg.initial_budget_cad}

    meta_currency = meta.set_index("Ticker")["Currency"].to_dict() if not meta.empty else {}

    holdings: dict[str, float] = {}
    cash = cfg.initial_budget_cad
    rebalance_set = set(rebalance_dates)
    rebalance_log = []

    daily_index = close.index[(close.index >= rebalance_dates[0]) & (close.index <= rebalance_dates[-1])]
    equity_records = []

    for date in daily_index:
        if date in rebalance_set:
            current_value = cash + sum(
                holdings.get(t, 0.0) * (_price_on(close, t, date) or 0.0) * (usd_to_cad if meta_currency.get(t) == "USD" else 1.0)
                for t in holdings
            )
            cfg_iter = dataclasses.replace(cfg, initial_budget_cad=current_value if current_value > 0 else cfg.initial_budget_cad)

            sliced_close = close.loc[:date]
            sliced_high = high.loc[:date]
            sliced_low = low.loc[:date]
            sliced_vol = vol.loc[:date]

            portfolio, meta_scored, meta_sel = compute_portfolio(sliced_close, sliced_high, sliced_low, sliced_vol, meta, cfg_iter, usd_to_cad)
            portfolio = apply_trading_fees(portfolio, cfg_iter, usd_to_cad)

            target_df = portfolio[portfolio["Ticker"] != "CASH"][["Ticker", "Shares"]] if not portfolio.empty else pd.DataFrame(columns=["Ticker", "Shares"])
            orders = compute_rebalance_orders(target_df, holdings)

            fees_cad = 0.0
            for order in orders:
                price_raw = _price_on(close, order.ticker, date)
                if price_raw is None:
                    continue  # no price data for this ticker on this date; skip the trade

                currency = meta_currency.get(order.ticker, "USD")
                price_cad = price_raw * usd_to_cad if currency == "USD" else price_raw
                trade_value_cad = order.qty * price_cad
                fees_cad += min(2.15, 0.001 * order.qty) * usd_to_cad

                if order.side == "buy":
                    cash -= trade_value_cad
                    holdings[order.ticker] = holdings.get(order.ticker, 0.0) + order.qty
                else:
                    cash += trade_value_cad
                    holdings[order.ticker] = holdings.get(order.ticker, 0.0) - order.qty
                    if abs(holdings[order.ticker]) < 1e-9:
                        del holdings[order.ticker]

            cash -= fees_cad
            rebalance_log.append({
                "date": date, "portfolio": portfolio, "meta_scored": meta_scored,
                "meta_sel": meta_sel, "n_orders": len(orders), "fees_cad": fees_cad,
            })

        equity = cash + sum(
            holdings.get(t, 0.0) * (_price_on(close, t, date) or 0.0) * (usd_to_cad if meta_currency.get(t) == "USD" else 1.0)
            for t in holdings
        )
        equity_records.append((date, equity))

    equity_curve = pd.Series(dict(equity_records)).sort_index()
    return {"equity_curve": equity_curve, "rebalance_log": rebalance_log, "final_holdings": holdings, "final_cash": cash}


def run_backtest(ticker_path: str, start: str, end: str, cfg: RaamConfig | None = None, freq: str = "ME") -> dict:
    """Downloads price data (with a lookback buffer before `start`) and runs the
    walk-forward backtest. Uses cfg.fallback_usd_to_cad as a constant FX rate rather
    than fetching today's live rate, since a historical backtest shouldn't depend on
    today's FX (that would be a form of lookahead, and adds an unnecessary network call
    per run rather than per rebalance).
    """
    cfg = cfg or RaamConfig()
    tickers = load_ticker_list(ticker_path)

    fetch_start = (pd.Timestamp(start) - pd.Timedelta(days=LOOKBACK_BUFFER_DAYS)).strftime("%Y-%m-%d")
    close, high, low, vol, meta = download_all_data(tickers, fetch_start, end)

    if close.empty:
        return {"equity_curve": pd.Series(dtype=float), "rebalance_log": [], "final_holdings": {}, "final_cash": cfg.initial_budget_cad}

    rebalance_dates = get_rebalance_dates(close.index, start, end, freq)
    return run_backtest_on_data(close, high, low, vol, meta, cfg, rebalance_dates, cfg.fallback_usd_to_cad)


def compute_metrics(equity_curve: pd.Series, risk_free: float = 0.0) -> dict:
    """CAGR, annualized volatility, Sharpe ratio, max drawdown, and % of positive months."""
    if equity_curve.empty or len(equity_curve) < 2:
        return {}

    n_days = len(equity_curve)
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
    years = n_days / TRADING_DAYS_PER_YEAR
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else float("nan")

    daily_returns = equity_curve.pct_change().dropna()
    annualized_vol = daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    excess_daily = daily_returns - risk_free / TRADING_DAYS_PER_YEAR
    sharpe = (excess_daily.mean() / daily_returns.std()) * np.sqrt(TRADING_DAYS_PER_YEAR) if daily_returns.std() else float("nan")

    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1
    max_drawdown = drawdown.min()

    monthly = equity_curve.resample("ME").last().pct_change().dropna()
    pct_positive_months = float((monthly > 0).mean()) if not monthly.empty else float("nan")

    return {
        "total_return": total_return,
        "cagr": cagr,
        "annualized_vol": annualized_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "pct_positive_months": pct_positive_months,
    }


def get_benchmark_equity_curve(ticker: str, start: str, end: str, initial_budget: float) -> pd.Series:
    """Buy-and-hold equity curve for a benchmark ticker (e.g. SPY) over the same window."""
    close, _, _, _, _ = download_all_data([ticker], start, end)
    if close.empty or ticker not in close.columns:
        return pd.Series(dtype=float)

    prices = close[ticker].dropna()
    if prices.empty:
        return pd.Series(dtype=float)

    shares = initial_budget / prices.iloc[0]
    return prices * shares
