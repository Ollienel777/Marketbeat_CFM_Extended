from unittest.mock import patch

import pytest

from raam.universe import get_sp500_tickers, load_sp500_fallback, normalize_ticker_for_yfinance


@pytest.mark.parametrize("symbol,expected", [
    ("BRK.B", "BRK-B"),
    ("brk.b", "BRK-B"),
    ("AAPL", "AAPL"),
    ("  aapl  ", "AAPL"),
    ("BF.B", "BF-B"),
])
def test_normalize_ticker_for_yfinance(symbol, expected):
    assert normalize_ticker_for_yfinance(symbol) == expected


@pytest.fixture
def fallback_csv(tmp_path):
    path = tmp_path / "fallback.csv"
    path.write_text("Ticker\nAAPL\nBRK.B\nKO\n")
    return str(path)


def test_load_sp500_fallback_normalizes_and_dedupes(fallback_csv):
    tickers = load_sp500_fallback(fallback_csv)
    assert tickers == ["AAPL", "BRK-B", "KO"]


def test_get_sp500_tickers_uses_live_source_when_fetch_succeeds():
    with patch("raam.universe.fetch_sp500_from_wikipedia", return_value=["AAPL", "KO"]):
        tickers, source = get_sp500_tickers()
    assert tickers == ["AAPL", "KO"]
    assert source == "live"


def test_get_sp500_tickers_falls_back_when_fetch_fails(fallback_csv):
    with patch("raam.universe.fetch_sp500_from_wikipedia", side_effect=RuntimeError("network down")):
        tickers, source = get_sp500_tickers(fallback_path=fallback_csv)
    assert tickers == ["AAPL", "BRK-B", "KO"]
    assert source == "fallback"
