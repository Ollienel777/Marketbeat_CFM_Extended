import numpy as np
import pandas as pd
import yfinance as yf

from raam.config import RaamConfig

# yfinance doesn't return a meaningful "sector" for ETFs (it comes back None/"Unknown"),
# which would lump every non-equity holding into one sector-cap bucket regardless of
# asset class. These overrides give each diversifying asset class its own bucket, the
# same way individual stock sectors get their own 40% cap -- so the strategy can
# actually rotate into bonds/commodities/real estate without that allocation being
# capped by however many other "Unknown"-sector tickers happen to be in the universe.
KNOWN_ASSET_CLASS_OVERRIDES = {
    "AGG": "Fixed Income",
    "IGOV": "Fixed Income",
    "TIP": "Fixed Income",
    "DBC": "Commodities",
    "VNQ": "Real Estate",
    "EFA": "International Equities",
    "EEM": "International Equities",
}


def resolve_sector(ticker: str, info_sector: str) -> str:
    """Applies the known asset-class override for ETFs lacking a real yfinance sector."""
    return KNOWN_ASSET_CLASS_OVERRIDES.get(ticker.upper(), info_sector)


def load_ticker_list(path: str) -> list[str]:
    if path.strip().upper() == "SP500":
        from raam.universe import get_sp500_tickers

        tickers, source = get_sp500_tickers()
        if source == "fallback":
            print("Warning: live S&P 500 list fetch failed; using the bundled fallback snapshot (may be stale).")
        return tickers

    df = pd.read_csv(path)
    col = df.columns[0]
    vals = df[col].dropna().astype(str).str.upper().str.strip().tolist()
    header = str(col).upper().strip()  # header might itself be a ticker

    if header not in vals:
        vals = [header] + vals

    return sorted(set(vals))


def download_all_data(tickers: list[str], start: str, end: str):
    raw = yf.download(
        tickers, start=start, end=end,
        auto_adjust=False, group_by="ticker",
        progress=False, threads=True,
    )

    if raw.empty:
        return (pd.DataFrame(),) * 5

    if isinstance(raw.columns, pd.MultiIndex):
        valid = [t for t in tickers if t in raw.columns.levels[0]]
        close = pd.DataFrame({t: raw[t]["Close"] for t in valid})
        high = pd.DataFrame({t: raw[t]["High"] for t in valid})
        low = pd.DataFrame({t: raw[t]["Low"] for t in valid})
        vol = pd.DataFrame({t: raw[t]["Volume"] for t in valid})
    else:
        t = tickers[0]
        close = raw[["Close"]].rename(columns={"Close": t})
        high = raw[["High"]].rename(columns={"High": t})
        low = raw[["Low"]].rename(columns={"Low": t})
        vol = raw[["Volume"]].rename(columns={"Volume": t})

    good = close.columns[close.notna().sum() > 0].tolist()
    close, high, low, vol = close[good], high[good], low[good], vol[good]

    rows = []
    for t in good:
        try:
            info = yf.Ticker(t).info
        except Exception:
            info = {}

        sector = resolve_sector(t, info.get("sector", "Unknown") or "Unknown")
        currency = info.get("currency", "USD") or "USD"
        mcap = info.get("marketCap", np.nan)
        country = info.get("country", None)
        exch = info.get("exchange", "")

        if country is None:
            if currency == "CAD" or "TSX" in str(exch) or str(exch).endswith(".TO"):
                country = "CA"
            else:
                country = "US"

        rows.append({
            "Ticker": t,
            "Sector": sector,
            "Currency": currency,
            "MarketCap": mcap,
            "Country": country,
        })

    meta = pd.DataFrame(rows)
    return close, high, low, vol, meta


def filter_universe(meta: pd.DataFrame, close: pd.DataFrame, vol: pd.DataFrame, cfg: RaamConfig) -> pd.DataFrame:
    if meta.empty:
        return meta

    # Currency (not Country) is the right filter here: it's reliably "USD"/"CAD" from
    # yfinance, whereas Country is the company's legal domicile (e.g. ACN reports
    # "Ireland" despite being a normal USD-denominated NYSE stock) and only ever came
    # back as the literal strings "US"/"CA" for tickers where yfinance returned no
    # country at all and our own fallback assigned one -- meaning this filter never
    # actually matched a real stock and was silently bypassed by the empty-result
    # fallback in compute_portfolio every time.
    meta = meta[meta["Currency"].isin(["USD", "CAD"])].copy()

    avg_vol = vol.mean()
    liquid = avg_vol[avg_vol >= cfg.min_liq_avg_volume].index
    meta = meta[meta["Ticker"].isin(liquid)].copy()

    needed = cfg.mom_lookback + 2
    hist_len = close.notna().sum()
    ok = hist_len[hist_len >= needed].index
    meta = meta[meta["Ticker"].isin(ok)].copy()

    return meta


def fetch_usd_to_cad(fallback: float) -> float:
    try:
        fx = yf.download("USDCAD=X", period="5d", progress=False, auto_adjust=True)["Close"].iloc[-1]
        if np.isnan(fx):
            return fallback
        return float(fx)
    except Exception:
        return fallback
