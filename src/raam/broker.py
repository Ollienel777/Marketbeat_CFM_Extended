import os
import re
from dataclasses import dataclass

import pandas as pd

# Tickers matching these patterns aren't tradable as US equities via IBKR's
# US stock routing: Canadian/other exchange suffixes (e.g. RY.TO, AIM.V),
# futures (GC=F), and crypto pairs (BTC-USD). CASH is our own sentinel row,
# not a broker symbol.
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
    """Connects to a locally running IBKR TWS or IB Gateway, in paper-trading mode.

    Requires TWS or IB Gateway to be running and logged into a *paper* account, with
    API access enabled (File/Configure > Settings > API > Enable ActiveX and Socket
    Clients). Connection details can be overridden via env vars:
      IBKR_HOST (default 127.0.0.1)
      IBKR_PORT (default 7497, TWS paper-trading port; IB Gateway paper is 4002)
      IBKR_CLIENT_ID (default 1)
    """
    from ib_async import IB

    host = os.environ.get("IBKR_HOST", "127.0.0.1")
    port = int(os.environ.get("IBKR_PORT", "7497"))
    client_id = int(os.environ.get("IBKR_CLIENT_ID", "1"))

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, readonly=False)
    except Exception as exc:
        raise RuntimeError(
            f"Could not connect to IBKR at {host}:{port} (client id {client_id}). "
            "Make sure TWS or IB Gateway is running, logged into your PAPER account, "
            "and has API access enabled (Configure > API > Settings)."
        ) from exc

    if not ib.isConnected():
        raise RuntimeError(f"Connected but IBKR session at {host}:{port} is not active.")

    accounts = ib.managedAccounts()
    if accounts and not any(acct.startswith("D") for acct in accounts):
        # IBKR paper accounts conventionally start with "D"; live accounts don't.
        raise RuntimeError(
            f"Connected IBKR account(s) {accounts} don't look like a paper account "
            "(paper account IDs start with 'D'). Refusing to trade -- reconnect to "
            "your paper-trading TWS/Gateway session instead."
        )

    return ib


def get_current_positions(client) -> dict[str, float]:
    from ib_async import Stock

    positions = client.positions()
    return {
        p.contract.symbol: float(p.position)
        for p in positions
        if isinstance(p.contract, Stock)
    }


def submit_orders(client, orders: list[RebalanceOrder]) -> None:
    from ib_async import MarketOrder, Stock

    for order in orders:
        contract = Stock(order.ticker, "SMART", "USD")
        client.qualifyContracts(contract)

        ib_order = MarketOrder(order.side.upper(), order.qty)
        client.placeOrder(contract, ib_order)
