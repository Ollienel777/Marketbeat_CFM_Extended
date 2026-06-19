import numpy as np
import pandas as pd

from raam.config import RaamConfig
from raam.factors import compute_momentum


def select_top_stocks(meta_scored: pd.DataFrame, cfg: RaamConfig) -> pd.DataFrame:
    if meta_scored.empty:
        return meta_scored.copy()

    df = meta_scored.sort_values("Score").copy()  # lower score = better rank

    chosen = []
    sector_w: dict[str, float] = {}
    # Each candidate's weight is judged against the target portfolio size, not the
    # count chosen so far -- using len(tmp) would make the very first pick "weigh"
    # 100% of a one-stock portfolio and always exceed the sector cap, disabling it.
    target_n = cfg.max_stocks

    for _, row in df.iterrows():
        t = row["Ticker"]
        s = row["Sector"]

        tmp = chosen + [t]
        if len(tmp) > cfg.max_stocks:
            break

        w = 1.0 / target_n
        sw = sector_w.copy()
        sw[s] = sw.get(s, 0) + w

        if max(sw.values()) > cfg.max_sector_weight:
            continue

        chosen.append(t)
        sector_w = sw

        if len(chosen) >= cfg.min_stocks:
            break

    if len(chosen) < cfg.min_stocks:
        chosen = df["Ticker"].head(cfg.min_stocks).tolist()

    return df[df["Ticker"].isin(chosen)].copy()


def optimize_sharpe(close: pd.DataFrame, meta_sel: pd.DataFrame, cfg: RaamConfig) -> pd.Series:
    tickers = meta_sel["Ticker"].tolist()
    n = len(tickers)
    if n == 0:
        return pd.Series(dtype=float)

    rets = close[tickers].pct_change(fill_method=None).dropna().tail(cfg.sharpe_lookback)
    if rets.empty:
        return pd.Series([1 / n] * n, index=tickers)

    mu = rets.mean()
    sigma = rets.cov()

    best_w, best_sh = None, -999.0
    rng = np.random.default_rng(42)

    for _ in range(cfg.sharpe_trials):
        w = rng.dirichlet(np.ones(n))
        if (w > cfg.max_stock_weight).any():
            continue
        if (w < (1 / (2 * n))).any():
            continue

        volp = np.sqrt(np.dot(w, sigma @ w))
        if volp == 0:
            continue

        sh = np.dot(w, mu) / volp
        if sh > best_sh:
            best_w, best_sh = w, sh

    if best_w is None:
        best_w = np.array([1 / n] * n)

    return pd.Series(best_w, index=tickers)


def apply_raam_sell_to_cash(close: pd.DataFrame, meta_sel: pd.DataFrame, weights: pd.Series, lookback: int):
    """RAAM absolute-momentum overlay: tickers with negative momentum are moved to cash."""
    if meta_sel.empty or weights.empty:
        return weights.copy(), 1.0

    tickers = meta_sel["Ticker"].tolist()
    close_sub = close[tickers].dropna(axis=1, how="all")

    if close_sub.empty or len(close_sub) <= lookback:
        return weights.copy() * 0, 1.0

    M_sel = compute_momentum(close_sub, lookback)

    neg = M_sel[M_sel < 0].index.tolist()
    pos = M_sel[M_sel >= 0].index.tolist()

    cash_w = float(weights.loc[neg].sum()) if len(neg) > 0 else 0.0

    new_w = weights.copy()
    new_w.loc[neg] = 0.0

    if len(pos) == 0:
        return new_w, 1.0

    return new_w, cash_w


def build_portfolio(close: pd.DataFrame, weights: pd.Series, meta_sel: pd.DataFrame, cfg: RaamConfig, usd_to_cad: float) -> pd.DataFrame:
    tickers = weights.index.tolist()
    last = close.iloc[-1][tickers]

    rows = []
    for t in tickers:
        row = meta_sel[meta_sel["Ticker"] == t].iloc[0]

        cur = str(row["Currency"]).upper()
        price = float(last[t])
        price_cad = price * usd_to_cad if cur == "USD" else price

        val_cad = float(weights[t]) * cfg.initial_budget_cad
        shares = val_cad / price_cad if price_cad > 0 else 0.0

        rows.append({
            "Ticker": t,
            "Sector": row["Sector"],
            "Currency": cur,
            "Price": price,
            "Shares": shares,
            "Weight": float(weights[t]),
            "Value": val_cad,
        })

    return pd.DataFrame(rows)
