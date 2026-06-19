import pandas as pd
import pytest

from raam.broker import compute_rebalance_orders, is_tradable, split_tradable


@pytest.mark.parametrize("ticker,expected", [
    ("AAPL", True),
    ("KO", True),
    ("BRK.B", False),    # exchange-suffix pattern also catches multi-class shares; treated conservatively
    ("RY.TO", False),
    ("AIM.V", False),
    ("HDFC.NS", False),
    ("GC=F", False),
    ("BTC-USD", False),
    ("CASH", False),
    ("cash", False),
])
def test_is_tradable(ticker, expected):
    assert is_tradable(ticker) == expected


def test_split_tradable_separates_rows():
    portfolio = pd.DataFrame({
        "Ticker": ["AAPL", "RY.TO", "GC=F", "CASH"],
        "Weight": [0.4, 0.3, 0.2, 0.1],
    })
    tradable, non_tradable = split_tradable(portfolio)

    assert list(tradable["Ticker"]) == ["AAPL"]
    assert set(non_tradable["Ticker"]) == {"RY.TO", "GC=F", "CASH"}


def test_compute_rebalance_orders_buys_new_positions():
    target = pd.DataFrame({"Ticker": ["AAPL", "KO"], "Shares": [100.0, 200.0]})
    orders = compute_rebalance_orders(target, current_positions={})

    by_ticker = {o.ticker: o for o in orders}
    assert by_ticker["AAPL"].side == "buy" and by_ticker["AAPL"].qty == 100.0
    assert by_ticker["KO"].side == "buy" and by_ticker["KO"].qty == 200.0


def test_compute_rebalance_orders_sells_dropped_positions():
    target = pd.DataFrame({"Ticker": ["AAPL"], "Shares": [100.0]})
    orders = compute_rebalance_orders(target, current_positions={"AAPL": 100.0, "KO": 50.0})

    by_ticker = {o.ticker: o for o in orders}
    assert "AAPL" not in by_ticker  # already at target, no order needed
    assert by_ticker["KO"].side == "sell" and by_ticker["KO"].qty == 50.0


def test_compute_rebalance_orders_adjusts_existing_position():
    target = pd.DataFrame({"Ticker": ["AAPL"], "Shares": [150.0]})
    orders = compute_rebalance_orders(target, current_positions={"AAPL": 100.0})

    assert len(orders) == 1
    assert orders[0].side == "buy"
    assert orders[0].qty == 50.0


def test_compute_rebalance_orders_skips_negligible_diff():
    target = pd.DataFrame({"Ticker": ["AAPL"], "Shares": [100.0]})
    orders = compute_rebalance_orders(target, current_positions={"AAPL": 100.0000001})
    assert orders == []
