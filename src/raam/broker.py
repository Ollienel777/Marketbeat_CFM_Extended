import os
import re
from dataclasses import dataclass

import pandas as pd

# Tickers matching these patterns aren't tradable as US equities via Alpaca:
# Canadian/other exchange suffixes (e.g. RY.TO, AIM.V), futures (GC=F), and
# crypto pairs (BTC-USD). CASH is our own sentinel row, not a broker symbol.
_NON_TRADABLE_PATTERNS = [
    re.compile(r"\.[A-Z]+$"),   # exchange suffix, e.g. .TO, .V, .NE, .NS
    re.compile(r"=F$"),         # futures, e.g. GC=F
    re.compile(r"-USD[T]?$"),   # crypto pairs, e.g. BTC-USD
]


def is_tradable(ticker: str) -> bool:
    if ticker.upper() == "CASH":
        return False
    return not any(p.search(ticker.upper()) for p in _NON_TRADABLE_PATTERNS)


@dataclass
class RebalanceOrder:
    ticker: str
    side: str  # "buy" or "sell"
    qty: float


def split_tradable(portfolio: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Splits a portfolio into (tradable, non_tradable) rows by ticker."""
    mask = portfolio["Ticker"].apply(is_tradable)
    return portfolio[mask].copy(), portfolio[~mask].copy()


def compute_rebalance_orders(target_portfolio: pd.DataFrame, current_positions: dict[str, float]) -> list[RebalanceOrder]:
    """Computes the buy/sell orders needed to move current_positions to target_portfolio.

    target_portfolio must already be filtered to tradable tickers (see split_tradable).
    current_positions maps ticker -> current quantity held (0 if not held).
    Tickers held currently but absent from the target are fully sold (target qty 0).
    """
    target_qty = {row["Ticker"]: float(row["Shares"]) for _, row in target_portfolio.iterrows()}

    all_tickers = set(target_qty) | set(current_positions)
    orders = []
    for ticker in sorted(all_tickers):
        target = target_qty.get(ticker, 0.0)
        current = current_positions.get(ticker, 0.0)
        diff = target - current

        if abs(diff) < 1e-6:
            continue

        orders.append(RebalanceOrder(ticker=ticker, side="buy" if diff > 0 else "sell", qty=abs(diff)))

    return orders


def get_trading_client():
    """Builds an Alpaca paper-trading client from ALPACA_API_KEY / ALPACA_SECRET_KEY env vars."""
    from alpaca.trading.client import TradingClient

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise RuntimeError(
            "Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables "
            "(use your Alpaca paper-trading keys, not live keys)."
        )

    return TradingClient(api_key, secret_key, paper=True)


def get_current_positions(client) -> dict[str, float]:
    positions = client.get_all_positions()
    return {p.symbol: float(p.qty) for p in positions}


def submit_orders(client, orders: list[RebalanceOrder]) -> None:
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    for order in orders:
        request = MarketOrderRequest(
            symbol=order.ticker,
            qty=order.qty,
            side=OrderSide.BUY if order.side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        client.submit_order(request)
