import numpy as np
import pandas as pd

from raam.config import RaamConfig
from raam.data import download_all_data, fetch_usd_to_cad, filter_universe, load_ticker_list
from raam.factors import compute_momentum, score_calc
from raam.portfolio import apply_raam_sell_to_cash, build_portfolio, optimize_sharpe, select_top_stocks


def run_raam_simple(ticker_path: str, start: str, end: str, cfg: RaamConfig):
    """Runs the RAAM pipeline and returns (portfolio, meta_scored, meta_sel) before fee scaling."""
    tickers = load_ticker_list(ticker_path)

    close, high, low, vol, meta = download_all_data(tickers, start, end)
    if close.empty or meta.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    meta2 = filter_universe(meta, close, vol, cfg)
    if meta2.empty:
        meta2 = meta[meta["Ticker"].isin(close.columns)].copy()

    meta_scored = score_calc(meta2, close, high, low, cfg)

    if meta_scored.empty:
        tickers_ok = meta2["Ticker"].tolist()
        prices_ok = close[tickers_ok].dropna(axis=1, how="all")

        if prices_ok.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        lb = min(cfg.mom_lookback, len(prices_ok) - 1)
        mom_simple = prices_ok.iloc[-1] / prices_ok.iloc[-(lb + 1)] - 1

        meta_scored = meta2.copy()
        meta_scored["Momentum"] = meta_scored["Ticker"].map(mom_simple)
        meta_scored["Volatility"] = np.nan
        meta_scored["AvgCorr"] = np.nan
        meta_scored["Trend"] = 0
        meta_scored["Score"] = (-meta_scored["Momentum"]).rank()

    meta_sel = select_top_stocks(meta_scored, cfg)

    weights = optimize_sharpe(close, meta_sel, cfg)
    weights, cash_w = apply_raam_sell_to_cash(close, meta_sel, weights, cfg.mom_lookback)

    weights_nonzero = weights[weights > 0]
    usd_to_cad = fetch_usd_to_cad(cfg.fallback_usd_to_cad)
    portfolio = build_portfolio(close, weights_nonzero, meta_sel, cfg, usd_to_cad)

    if cash_w > 0:
        cash_row = pd.DataFrame([{
            "Ticker": "CASH",
            "Sector": "Cash",
            "Currency": "CAD",
            "Price": np.nan,
            "Shares": 0.0,
            "Weight": cash_w,
            "Value": cash_w * cfg.initial_budget_cad,
        }])
        portfolio = pd.concat([portfolio, cash_row], ignore_index=True)

    return portfolio, meta_scored, meta_sel


def apply_trading_fees(portfolio: pd.DataFrame, cfg: RaamConfig) -> pd.DataFrame:
    """Scales the portfolio down so its net value (after per-trade fees) matches the budget."""
    if portfolio.empty:
        return portfolio.copy()

    fees_usd = np.minimum(2.15, 0.001 * portfolio["Shares"].abs())
    total_fee_usd = fees_usd.sum()

    usd_to_cad = fetch_usd_to_cad(cfg.fallback_usd_to_cad)
    total_fee_cad = total_fee_usd * usd_to_cad

    gross_value_cad = portfolio["Value"].sum()
    net_portfolio_value_cad = cfg.initial_budget_cad - total_fee_cad
    scale = net_portfolio_value_cad / gross_value_cad if gross_value_cad else 1.0

    out = portfolio.copy()
    out["Shares"] = out["Shares"] * scale
    out["Value"] = out["Value"] * scale
    out["Weight"] = out["Value"] / net_portfolio_value_cad

    return out


def run_raam(ticker_path: str, start: str, end: str, cfg: RaamConfig | None = None):
    """Full pipeline: ranking + selection + sizing + fee-adjusted final portfolio.

    Returns (portfolio_final, meta_scored, meta_sel).
    """
    cfg = cfg or RaamConfig()
    portfolio, meta_scored, meta_sel = run_raam_simple(ticker_path, start, end, cfg)
    portfolio_final = apply_trading_fees(portfolio, cfg)
    return portfolio_final, meta_scored, meta_sel
