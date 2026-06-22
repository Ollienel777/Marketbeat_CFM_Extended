import io

import pandas as pd
import requests

SP500_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP500_FALLBACK_PATH = "sp500_fallback.csv"

# Wikipedia's table normally fails a bare urllib/pandas fetch with HTTP 403 -- it
# rejects requests with no User-Agent header. A plain browser-like UA is enough.
_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; raam-research-bot/1.0)"}


def normalize_ticker_for_yfinance(symbol: str) -> str:
    """Wikipedia uses dots for share classes (e.g. BRK.B); yfinance expects dashes (BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def fetch_sp500_from_wikipedia() -> list[str]:
    """Scrapes the current S&P 500 constituent list from Wikipedia. Raises on any failure
    (network error, HTTP error, unexpected table layout) -- callers should catch and fall
    back to load_sp500_fallback() rather than letting an unattended run crash on this."""
    response = requests.get(SP500_WIKIPEDIA_URL, headers=_REQUEST_HEADERS, timeout=15)
    response.raise_for_status()

    tables = pd.read_html(io.StringIO(response.text))
    df = tables[0]
    if "Symbol" not in df.columns:
        raise ValueError("Expected a 'Symbol' column in the Wikipedia S&P 500 table; layout may have changed.")

    tickers = sorted({normalize_ticker_for_yfinance(s) for s in df["Symbol"].dropna()})
    if len(tickers) < 400:  # sanity check -- a real pull should be ~500
        raise ValueError(f"Only parsed {len(tickers)} tickers; this looks like a broken/partial table.")

    return tickers


def load_sp500_fallback(path: str = SP500_FALLBACK_PATH) -> list[str]:
    """Reads the bundled, one-time-captured S&P 500 snapshot used when the live
    Wikipedia scrape fails. This is intentionally static -- it's a safety net, not
    something refreshed automatically, so it won't silently go stale in a way that
    surprises anyone relying on it."""
    df = pd.read_csv(path)
    col = df.columns[0]
    return sorted({normalize_ticker_for_yfinance(s) for s in df[col].dropna().astype(str)})


def get_sp500_tickers(fallback_path: str = SP500_FALLBACK_PATH) -> tuple[list[str], str]:
    """Returns (tickers, source) where source is 'live' (Wikipedia) or 'fallback'
    (bundled snapshot, used because the live pull failed)."""
    try:
        return fetch_sp500_from_wikipedia(), "live"
    except Exception:
        return load_sp500_fallback(fallback_path), "fallback"
