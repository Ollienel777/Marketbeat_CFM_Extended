import argparse
import sys

from raam.history import (
    DEFAULT_DB_PATH,
    get_run_positions,
    get_ticker_history,
    list_account_snapshots,
    list_backtest_runs,
    list_runs,
)


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="raam-history", description="Inspect recorded RAAM strategy runs.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite history DB path.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all recorded runs.")

    show = sub.add_parser("show", help="Show the positions for one run.")
    show.add_argument("run_id", type=int)

    ticker = sub.add_parser("ticker", help="Show a ticker's position across every recorded run.")
    ticker.add_argument("symbol")

    sub.add_parser("pnl", help="Show the IBKR paper account's equity/P&L over time (from raam-trade snapshots).")

    sub.add_parser("backtests", help="List all recorded backtest runs, for comparing across versions.")

    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "list":
        runs = list_runs(args.db)
        if runs.empty:
            print("No runs recorded yet.")
            return 0
        print(runs.to_string(index=False))
        return 0

    if args.command == "show":
        positions = get_run_positions(args.db, args.run_id)
        if positions.empty:
            print(f"No positions found for run #{args.run_id}.", file=sys.stderr)
            return 1
        print(positions.to_string(index=False))
        return 0

    if args.command == "ticker":
        history = get_ticker_history(args.db, args.symbol)
        if history.empty:
            print(f"No history found for {args.symbol.upper()}.", file=sys.stderr)
            return 1
        print(history.to_string(index=False))
        return 0

    if args.command == "pnl":
        snapshots = list_account_snapshots(args.db)
        if snapshots.empty:
            print("No account snapshots recorded yet. Run `raam-trade` (it snapshots automatically).", file=sys.stderr)
            return 1

        print(snapshots.to_string(index=False))

        first_nl = snapshots["net_liquidation"].dropna()
        if len(first_nl) >= 2:
            change = first_nl.iloc[-1] - first_nl.iloc[0]
            pct = (change / first_nl.iloc[0]) * 100 if first_nl.iloc[0] else 0.0
            print(f"\nNet change since first snapshot: ${change:,.2f} ({pct:+.2f}%)")
        return 0

    if args.command == "backtests":
        backtests = list_backtest_runs(args.db)
        if backtests.empty:
            print("No backtests recorded yet. Run `raam-backtest`.", file=sys.stderr)
            return 1
        print(backtests.to_string(index=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
