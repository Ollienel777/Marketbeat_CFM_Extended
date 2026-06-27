import argparse
import sys
from pathlib import Path

from raam.history import DEFAULT_DB_PATH
from raam.sweep import DEFAULT_WINDOWS, run_sweep, summarize_sweep


def _parse_window(text: str) -> tuple[str, str]:
    start, end = text.split(":")
    return start.strip(), end.strip()


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="raam-sweep", description="Sweep concentration parameters (max_stocks, sector/stock caps) across multiple backtest windows."
    )
    parser.add_argument("--tickers", required=True, help="Path to a CSV file of candidate tickers (or 'SP500').")
    parser.add_argument(
        "--window", action="append", dest="windows", type=_parse_window,
        help="A 'start:end' window (YYYY-MM-DD:YYYY-MM-DD). Repeatable. Defaults to 4 built-in non-overlapping windows.",
    )
    parser.add_argument("--budget", type=float, default=1_000_000, help="Initial budget in CAD per backtest.")
    parser.add_argument("--sharpe-trials", type=int, default=5_000, help="Random search trials for the Sharpe optimizer (reduced from the live default to keep the sweep's runtime reasonable).")
    parser.add_argument("--benchmark", default="SPY", help="Buy-and-hold benchmark ticker.")
    parser.add_argument("--label-prefix", default="sweep", help="Prefix for each recorded backtest's label.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite history DB path to record results into.")
    parser.add_argument("--no-record", action="store_true", help="Don't record results to the history DB (only write the summary CSV).")
    parser.add_argument("--out", default="sweep_results", help="Directory to write the full results and summary CSVs to.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    windows = args.windows or DEFAULT_WINDOWS

    print(f"Sweeping concentration parameters over {len(windows)} window(s): {windows}")
    results = run_sweep(
        ticker_path=args.tickers, windows=windows, sharpe_trials=args.sharpe_trials,
        budget=args.budget, benchmark=args.benchmark, label_prefix=args.label_prefix,
        db_path=args.db, record=not args.no_record,
    )

    if results.empty:
        print("Sweep produced no results (no usable price data for this universe/windows).", file=sys.stderr)
        return 1

    summary = summarize_sweep(results)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "sweep_results_full.csv"
    summary_path = out_dir / "sweep_results_summary.csv"
    results.to_csv(results_path, index=False)
    summary.to_csv(summary_path, index=False)

    print(f"\nTop 10 combinations by average Sharpe across {len(windows)} window(s):")
    print(summary.head(10).to_string(index=False))
    print(f"\nWrote full per-window results to {results_path}")
    print(f"Wrote ranked summary to {summary_path}")

    if not args.no_record:
        print(f"Recorded {len(results)} labeled backtests to {args.db} -- view them in the dashboard's Backtest comparison page.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
