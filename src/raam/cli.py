import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from raam.config import RaamConfig
from raam.history import DEFAULT_DB_PATH, record_run
from raam.strategy import run_raam


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="raam", description="Run the RAAM portfolio strategy.")
    parser.add_argument("--tickers", required=True, help="Path to a CSV file of candidate tickers.")
    parser.add_argument("--start", default="2024-10-01", help="Price history start date (YYYY-MM-DD).")
    parser.add_argument("--end", default=date.today().isoformat(), help="Price history end date (YYYY-MM-DD).")
    parser.add_argument("--budget", type=float, default=1_000_000, help="Initial budget in CAD.")
    parser.add_argument("--out", default="results", help="Directory to write output CSVs to.")
    parser.add_argument("--history-db", default=DEFAULT_DB_PATH, help="SQLite DB path to record this run into.")
    parser.add_argument("--no-history", action="store_true", help="Skip recording this run to the history DB.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    cfg = RaamConfig(initial_budget_cad=args.budget)
    portfolio, meta_scored, meta_sel = run_raam(args.tickers, args.start, args.end, cfg)

    if portfolio.empty:
        print("No portfolio could be constructed (no usable tickers/price data).", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    portfolio_path = out_dir / f"portfolio_{stamp}.csv"
    scored_path = out_dir / f"scored_universe_{stamp}.csv"

    portfolio.to_csv(portfolio_path, index=False)
    meta_scored.to_csv(scored_path, index=False)

    print(f"Budget (CAD): {cfg.initial_budget_cad:,.0f}")
    print(f"Selected {len(meta_sel)} stocks from a universe of {len(meta_scored)}.")
    print(portfolio.sort_values("Weight", ascending=False).to_string(index=False))
    print(f"\nWrote portfolio to {portfolio_path}")
    print(f"Wrote scored universe to {scored_path}")

    if not args.no_history:
        run_id = record_run(
            db_path=args.history_db,
            run_at=datetime.now().isoformat(timespec="seconds"),
            tickers_path=args.tickers,
            start_date=args.start,
            end_date=args.end,
            budget_cad=cfg.initial_budget_cad,
            universe_size=len(meta_scored),
            portfolio=portfolio,
        )
        print(f"Recorded run #{run_id} to {args.history_db}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
