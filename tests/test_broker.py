from dataclasses import dataclass

import pandas as pd
import pytest

from raam.broker import (
    RebalanceOrder,
    compute_rebalance_orders,
    get_account_summary,
    is_tradable,
    round_to_whole_shares,
    split_tradable,
)


@dataclass
class _FakeAccountValue:
    account: str
    tag: str
    value: str


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


def test_round_to_whole_shares_floors_quantities():
    orders = [RebalanceOrder("AAPL", "buy", 180.2393), RebalanceOrder("KO", "sell", 1173.1895)]
    rounded = round_to_whole_shares(orders)

    by_ticker = {o.ticker: o for o in rounded}
    assert by_ticker["AAPL"].qty == 180.0
    assert by_ticker["KO"].qty == 1173.0
    assert by_ticker["AAPL"].side == "buy"
    assert by_ticker["KO"].side == "sell"


def test_round_to_whole_shares_drops_orders_under_one_share():
    orders = [RebalanceOrder("AAPL", "buy", 0.6), RebalanceOrder("KO", "buy", 1.2)]
    rounded = round_to_whole_shares(orders)

    assert [o.ticker for o in rounded] == ["KO"]
    assert rounded[0].qty == 1.0


class _FakeAccountClient:
    def __init__(self, values):
        self._values = values

    def accountSummary(self):
        return self._values


def test_get_account_summary_parses_known_tags():
    client = _FakeAccountClient([
        _FakeAccountValue("DU12345", "NetLiquidation", "1005000.00"),
        _FakeAccountValue("DU12345", "TotalCashValue", "200000.00"),
        _FakeAccountValue("DU12345", "GrossPositionValue", "805000.00"),
        _FakeAccountValue("DU12345", "UnrealizedPnL", "5000.00"),
        _FakeAccountValue("DU12345", "RealizedPnL", "0.00"),
        _FakeAccountValue("DU12345", "SomeOtherTag", "ignored"),
    ])

    summary = get_account_summary(client)

    assert summary["account_id"] == "DU12345"
    assert summary["net_liquidation"] == 1_005_000.0
    assert summary["cash_balance"] == 200_000.0
    assert summary["gross_position_value"] == 805_000.0
    assert summary["unrealized_pnl"] == 5_000.0
    assert summary["realized_pnl"] == 0.0


def test_get_account_summary_handles_missing_tags():
    client = _FakeAccountClient([_FakeAccountValue("DU12345", "NetLiquidation", "1000000.00")])

    summary = get_account_summary(client)

    assert summary["account_id"] == "DU12345"
    assert summary["net_liquidation"] == 1_000_000.0
    assert summary["cash_balance"] is None
    assert summary["unrealized_pnl"] is None


def test_get_account_summary_empty_client():
    summary = get_account_summary(_FakeAccountClient([]))
    assert summary["account_id"] is None
    assert summary["net_liquidation"] is None
