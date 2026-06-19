import pandas as pd
import pytest

from raam.history import get_run_positions, get_ticker_history, list_runs, record_run


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "history.db")


@pytest.fixture
def sample_portfolio():
    return pd.DataFrame([
        {"Ticker": "AAPL", "Sector": "Technology", "Currency": "USD", "Price": 200.0,
         "Shares": 100.0, "Weight": 0.5, "Value": 500_000.0},
        {"Ticker": "KO", "Sector": "Consumer Defensive", "Currency": "USD", "Price": 70.0,
         "Shares": 700.0, "Weight": 0.5, "Value": 500_000.0},
    ])


def test_record_run_creates_run_and_positions(db_path, sample_portfolio):
    run_id = record_run(
        db_path=db_path, run_at="2026-06-19T10:00:00", tickers_path="tickers.csv",
        start_date="2024-10-01", end_date="2025-11-21", budget_cad=1_000_000,
        universe_size=37, portfolio=sample_portfolio,
    )

    runs = list_runs(db_path)
    assert len(runs) == 1
    assert runs.iloc[0]["run_id"] == run_id
    assert runs.iloc[0]["selected_size"] == 2

    positions = get_run_positions(db_path, run_id)
    assert set(positions["ticker"]) == {"AAPL", "KO"}


def test_record_run_accumulates_across_multiple_runs(db_path, sample_portfolio):
    run_id_1 = record_run(
        db_path=db_path, run_at="2026-06-19T10:00:00", tickers_path="tickers.csv",
        start_date="2024-10-01", end_date="2025-11-21", budget_cad=1_000_000,
        universe_size=37, portfolio=sample_portfolio,
    )
    run_id_2 = record_run(
        db_path=db_path, run_at="2026-06-26T10:00:00", tickers_path="tickers.csv",
        start_date="2024-10-01", end_date="2025-11-28", budget_cad=1_000_000,
        universe_size=40, portfolio=sample_portfolio,
    )

    assert run_id_2 == run_id_1 + 1
    assert len(list_runs(db_path)) == 2


def test_get_ticker_history_spans_runs(db_path, sample_portfolio):
    record_run(
        db_path=db_path, run_at="2026-06-19T10:00:00", tickers_path="tickers.csv",
        start_date="2024-10-01", end_date="2025-11-21", budget_cad=1_000_000,
        universe_size=37, portfolio=sample_portfolio,
    )
    record_run(
        db_path=db_path, run_at="2026-06-26T10:00:00", tickers_path="tickers.csv",
        start_date="2024-10-01", end_date="2025-11-28", budget_cad=1_000_000,
        universe_size=40, portfolio=sample_portfolio,
    )

    history = get_ticker_history(db_path, "aapl")  # lowercase input should still match
    assert len(history) == 2
    assert list(history["run_at"]) == ["2026-06-19T10:00:00", "2026-06-26T10:00:00"]


def test_get_ticker_history_empty_for_unknown_ticker(db_path, sample_portfolio):
    record_run(
        db_path=db_path, run_at="2026-06-19T10:00:00", tickers_path="tickers.csv",
        start_date="2024-10-01", end_date="2025-11-21", budget_cad=1_000_000,
        universe_size=37, portfolio=sample_portfolio,
    )
    assert get_ticker_history(db_path, "ZZZZ").empty
