import pandas as pd

from raam.config import RaamConfig
from raam.portfolio import select_top_stocks


def test_select_top_stocks_respects_sector_cap():
    # max_stocks=10 with a 40% sector cap means at most 4 stocks (4/10) from
    # any one sector should be admitted via the capped path (not the fallback).
    # min_stocks == max_stocks so the early-stop-once-min-reached logic doesn't
    # cut the run short before the cap has a chance to bind.
    cfg = RaamConfig(min_stocks=10, max_stocks=10, max_sector_weight=0.40)

    tickers, sectors, scores = [], [], []
    i = 0
    for round_ in range(4):
        for s in ["A", "B", "C"]:
            tickers.append(f"{s}{round_}")
            sectors.append(s)
            scores.append(i)
            i += 1

    meta_scored = pd.DataFrame({"Ticker": tickers, "Sector": sectors, "Score": scores})

    selected = select_top_stocks(meta_scored, cfg)
    sector_counts = selected["Sector"].value_counts()

    assert len(selected) == cfg.max_stocks
    assert sector_counts.max() <= 4  # floor(0.40 * 10)


def test_select_top_stocks_falls_back_when_caps_block_min_stocks():
    cfg = RaamConfig(min_stocks=4, max_stocks=10, max_sector_weight=0.40)

    # Only 3 sectors available; a strict cap would never reach min_stocks=4
    # with 3 stocks per sector at 0.40 max weight, so fallback kicks in.
    meta_scored = pd.DataFrame({
        "Ticker": ["A", "B", "C"],
        "Sector": ["Tech", "Health", "Energy"],
        "Score": [1, 2, 3],
    })

    selected = select_top_stocks(meta_scored, cfg)
    assert len(selected) == 3  # fallback returns head(min_stocks), capped by availability
