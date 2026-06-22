from unittest.mock import patch

import pytest

from raam.data import load_ticker_list, resolve_sector


@pytest.mark.parametrize("ticker,expected", [
    ("AGG", "Fixed Income"),
    ("agg", "Fixed Income"),    # case-insensitive
    ("IGOV", "Fixed Income"),
    ("TIP", "Fixed Income"),
    ("DBC", "Commodities"),
    ("VNQ", "Real Estate"),
    ("EFA", "International Equities"),
    ("EEM", "International Equities"),
])
def test_resolve_sector_overrides_known_etfs(ticker, expected):
    assert resolve_sector(ticker, "Unknown") == expected


def test_resolve_sector_passes_through_unknown_tickers():
    assert resolve_sector("AAPL", "Technology") == "Technology"


def test_resolve_sector_passes_through_when_no_override_exists():
    assert resolve_sector("SOME_NEW_TICKER", "Unknown") == "Unknown"


@pytest.mark.parametrize("sentinel", ["SP500", "sp500", "  SP500  "])
def test_load_ticker_list_recognizes_sp500_sentinel(sentinel):
    with patch("raam.universe.get_sp500_tickers", return_value=(["AAPL", "KO"], "live")):
        assert load_ticker_list(sentinel) == ["AAPL", "KO"]


def test_load_ticker_list_warns_on_fallback(capsys):
    with patch("raam.universe.get_sp500_tickers", return_value=(["AAPL"], "fallback")):
        load_ticker_list("SP500")
    assert "fallback" in capsys.readouterr().out.lower()


def test_load_ticker_list_still_reads_csv_files_normally(tmp_path):
    csv_path = tmp_path / "tickers.csv"
    csv_path.write_text("Ticker\nAAPL\nKO\n")
    assert load_ticker_list(str(csv_path)) == ["AAPL", "KO", "TICKER"]
