import pandas as pd
import pytest

from raam.history import (
    get_backtest_equity_curve,
    get_run_positions,
    get_run_scored_universe,
    get_ticker_history,
    list_account_snapshots,
    list_backtest_runs,
    list_runs,
    record_account_snapshot,
    record_backtest_run,
    record_run,
)


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


def test_record_run_persists_scored_universe(db_path, sample_portfolio):
    meta_scored = pd.DataFrame([
        {"Ticker": "AAPL", "Sector": "Technology", "Momentum": 0.12, "Volatility": 0.02,
         "AvgCorr": 0.3, "Trend": 0, "Score": 1.5},
        {"Ticker": "KO", "Sector": "Consumer Defensive", "Momentum": 0.05, "Volatility": 0.01,
         "AvgCorr": 0.2, "Trend": 0, "Score": 2.5},
        {"Ticker": "XOM", "Sector": "Energy", "Momentum": -0.03, "Volatility": 0.03,
         "AvgCorr": 0.1, "Trend": -1, "Score": 5.0},
    ])

    run_id = record_run(
        db_path=db_path, run_at="2026-06-19T10:00:00", tickers_path="tickers.csv",
        start_date="2024-10-01", end_date="2025-11-21", budget_cad=1_000_000,
        universe_size=3, portfolio=sample_portfolio, meta_scored=meta_scored,
    )

    universe = get_run_scored_universe(db_path, run_id)
    assert len(universe) == 3
    assert set(universe["ticker"]) == {"AAPL", "KO", "XOM"}
    assert universe.iloc[0]["ticker"] == "AAPL"  # ordered by score ascending


def test_record_run_without_meta_scored_leaves_universe_empty(db_path, sample_portfolio):
    run_id = record_run(
        db_path=db_path, run_at="2026-06-19T10:00:00", tickers_path="tickers.csv",
        start_date="2024-10-01", end_date="2025-11-21", budget_cad=1_000_000,
        universe_size=2, portfolio=sample_portfolio,
    )
    assert get_run_scored_universe(db_path, run_id).empty


def test_record_account_snapshot_round_trips(db_path):
    snapshot_id = record_account_snapshot(
        db_path=db_path, snapshot_at="2026-06-19T10:00:00", account_id="DU12345",
        net_liquidation=1_005_000.0, cash_balance=200_000.0, gross_position_value=805_000.0,
        unrealized_pnl=5_000.0, realized_pnl=0.0,
    )

    snapshots = list_account_snapshots(db_path)
    assert len(snapshots) == 1
    assert snapshots.iloc[0]["snapshot_id"] == snapshot_id
    assert snapshots.iloc[0]["account_id"] == "DU12345"
    assert snapshots.iloc[0]["net_liquidation"] == 1_005_000.0


def test_list_account_snapshots_orders_chronologically(db_path):
    record_account_snapshot(
        db_path=db_path, snapshot_at="2026-06-19T10:00:00", account_id="DU12345",
        net_liquidation=1_000_000.0, cash_balance=1_000_000.0, gross_position_value=0.0,
        unrealized_pnl=0.0, realized_pnl=0.0,
    )
    record_account_snapshot(
        db_path=db_path, snapshot_at="2026-06-26T10:00:00", account_id="DU12345",
        net_liquidation=1_010_000.0, cash_balance=200_000.0, gross_position_value=810_000.0,
        unrealized_pnl=10_000.0, realized_pnl=0.0,
    )

    snapshots = list_account_snapshots(db_path)
    assert list(snapshots["net_liquidation"]) == [1_000_000.0, 1_010_000.0]


def test_list_account_snapshots_empty_db(db_path):
    assert list_account_snapshots(db_path).empty


@pytest.fixture
def sample_equity_curve():
    idx = pd.bdate_range("2024-01-02", periods=5)
    return pd.Series([100_000.0, 101_000.0, 99_500.0, 102_000.0, 103_000.0], index=idx)


@pytest.fixture
def sample_benchmark_curve():
    idx = pd.bdate_range("2024-01-02", periods=5)
    return pd.Series([100_000.0, 100_500.0, 101_000.0, 101_500.0, 102_000.0], index=idx)


def test_record_backtest_run_persists_metrics_and_curve(db_path, sample_equity_curve, sample_benchmark_curve):
    backtest_id = record_backtest_run(
        db_path=db_path, run_at="2026-06-20T10:00:00", label="v1-baseline",
        tickers_path="tickers.csv", start_date="2024-01-01", end_date="2024-01-08",
        budget_cad=100_000, freq="ME", benchmark_ticker="SPY", total_fees_cad=12.50,
        strategy_metrics={"total_return": 0.03, "cagr": 0.5, "annualized_vol": 0.1, "sharpe": 1.2, "max_drawdown": -0.015, "pct_positive_months": 1.0},
        benchmark_metrics={"total_return": 0.02, "cagr": 0.4, "annualized_vol": 0.08, "sharpe": 1.1, "max_drawdown": -0.005, "pct_positive_months": 1.0},
        equity_curve=sample_equity_curve, benchmark_curve=sample_benchmark_curve,
    )

    backtests = list_backtest_runs(db_path)
    assert len(backtests) == 1
    assert backtests.iloc[0]["backtest_id"] == backtest_id
    assert backtests.iloc[0]["label"] == "v1-baseline"
    assert backtests.iloc[0]["strategy_cagr"] == 0.5

    curve = get_backtest_equity_curve(db_path, backtest_id)
    assert len(curve) == 5
    assert curve.iloc[0]["strategy_value"] == 100_000.0
    assert curve.iloc[-1]["benchmark_value"] == 102_000.0


def test_record_backtest_run_accumulates_across_versions(db_path, sample_equity_curve, sample_benchmark_curve):
    for label in ["v1-baseline", "v2-ewma-vol"]:
        record_backtest_run(
            db_path=db_path, run_at="2026-06-20T10:00:00", label=label,
            tickers_path="tickers.csv", start_date="2024-01-01", end_date="2024-01-08",
            budget_cad=100_000, freq="ME", benchmark_ticker="SPY", total_fees_cad=10.0,
            strategy_metrics={"total_return": 0.03, "cagr": 0.5, "annualized_vol": 0.1, "sharpe": 1.2, "max_drawdown": -0.01, "pct_positive_months": 1.0},
            benchmark_metrics={}, equity_curve=sample_equity_curve, benchmark_curve=pd.Series(dtype=float),
        )

    backtests = list_backtest_runs(db_path)
    assert list(backtests["label"]) == ["v1-baseline", "v2-ewma-vol"]


def test_record_backtest_run_handles_empty_benchmark(db_path, sample_equity_curve):
    backtest_id = record_backtest_run(
        db_path=db_path, run_at="2026-06-20T10:00:00", label=None,
        tickers_path="tickers.csv", start_date="2024-01-01", end_date="2024-01-08",
        budget_cad=100_000, freq="ME", benchmark_ticker="SPY", total_fees_cad=0.0,
        strategy_metrics={"total_return": 0.03, "cagr": 0.5, "annualized_vol": 0.1, "sharpe": 1.2, "max_drawdown": -0.01, "pct_positive_months": 1.0},
        benchmark_metrics={}, equity_curve=sample_equity_curve, benchmark_curve=pd.Series(dtype=float),
    )

    curve = get_backtest_equity_curve(db_path, backtest_id)
    assert curve["benchmark_value"].isna().all()


def test_list_backtest_runs_empty_db(db_path):
    assert list_backtest_runs(db_path).empty


def test_get_backtest_equity_curve_unknown_id(db_path):
    assert get_backtest_equity_curve(db_path, 999).empty
