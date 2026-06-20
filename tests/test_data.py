import pytest

from raam.data import resolve_sector


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
