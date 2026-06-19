import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

DEFAULT_DB_PATH = "raam_history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    tickers_path TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    budget_cad REAL NOT NULL,
    universe_size INTEGER NOT NULL,
    selected_size INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    run_id INTEGER NOT NULL REFERENCES runs(run_id),
    ticker TEXT NOT NULL,
    sector TEXT,
    currency TEXT,
    price REAL,
    shares REAL,
    weight REAL,
    value REAL
);

CREATE TABLE IF NOT EXISTS scored_universe (
    run_id INTEGER NOT NULL REFERENCES runs(run_id),
    ticker TEXT NOT NULL,
    sector TEXT,
    momentum REAL,
    volatility REAL,
    avg_corr REAL,
    trend REAL,
    score REAL
);
"""


@contextmanager
def _connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_run(
    db_path: str,
    run_at: str,
    tickers_path: str,
    start_date: str,
    end_date: str,
    budget_cad: float,
    universe_size: int,
    portfolio: pd.DataFrame,
    meta_scored: pd.DataFrame | None = None,
) -> int:
    """Persists one strategy run (metadata, resulting positions, and optionally the
    full scored universe used to make the selection). Returns the run_id."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO runs (run_at, tickers_path, start_date, end_date, budget_cad, "
            "universe_size, selected_size) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_at, tickers_path, start_date, end_date, budget_cad, universe_size, len(portfolio)),
        )
        run_id = cur.lastrowid

        rows = [
            (
                run_id,
                row.get("Ticker"),
                row.get("Sector"),
                row.get("Currency"),
                row.get("Price"),
                row.get("Shares"),
                row.get("Weight"),
                row.get("Value"),
            )
            for row in portfolio.to_dict("records")
        ]
        conn.executemany(
            "INSERT INTO positions (run_id, ticker, sector, currency, price, shares, weight, value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        if meta_scored is not None and not meta_scored.empty:
            scored_rows = [
                (
                    run_id,
                    row.get("Ticker"),
                    row.get("Sector"),
                    row.get("Momentum"),
                    row.get("Volatility"),
                    row.get("AvgCorr"),
                    row.get("Trend"),
                    row.get("Score"),
                )
                for row in meta_scored.to_dict("records")
            ]
            conn.executemany(
                "INSERT INTO scored_universe (run_id, ticker, sector, momentum, volatility, avg_corr, "
                "trend, score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                scored_rows,
            )

    return run_id


def list_runs(db_path: str) -> pd.DataFrame:
    with _connect(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM runs ORDER BY run_id", conn)


def get_run_positions(db_path: str, run_id: int) -> pd.DataFrame:
    with _connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM positions WHERE run_id = ? ORDER BY weight DESC", conn, params=(run_id,)
        )


def get_run_scored_universe(db_path: str, run_id: int) -> pd.DataFrame:
    with _connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM scored_universe WHERE run_id = ? ORDER BY score", conn, params=(run_id,)
        )


def get_ticker_history(db_path: str, ticker: str) -> pd.DataFrame:
    """Returns every run's position (if any) for a given ticker, joined with run dates."""
    with _connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT runs.run_at, positions.* FROM positions "
            "JOIN runs ON runs.run_id = positions.run_id "
            "WHERE positions.ticker = ? ORDER BY runs.run_id",
            conn,
            params=(ticker.upper(),),
        )
