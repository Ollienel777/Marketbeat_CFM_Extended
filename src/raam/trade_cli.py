import argparse
import sys

from raam.broker import compute_rebalance_orders, get_current_positions, get_trading_client, split_tradable, submit_orders
from raam.history import DEFAULT_DB_PATH, get_run_positions, list_runs


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="raam-trade", description="Sync an IBKR paper-trading account to a recorded RAAM run."
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite history DB path.")
    parser.add_argument("--run-id", type=int, default=None, help="Run to sync to. Defaults to the latest run.")
    parser.add_argument("--execute", action="store_true", help="Actually submit orders. Without this, it's a dry run.")
    return parser.parse_args(argv)


def _resolve_run_id(db_path: str, run_id: int | None) -> int | None:
    if run_id is not None:
        return run_id
    runs = list_runs(db_path)
    if runs.empty:
        return None
    return int(runs.iloc[-1]["run_id"])


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    run_id = _resolve_run_id(args.db, args.run_id)
    if run_id is None:
        print("No recorded runs found. Run `raam` first.", file=sys.stderr)
        return 1

    portfolio = get_run_positions(args.db, run_id)
    if portfolio.empty:
        print(f"Run #{run_id} has no positions.", file=sys.stderr)
        return 1

    # history.py lowercases the column names (sqlite read); broker.py expects the
    # same Ticker/Shares casing used by the strategy's portfolio DataFrame.
    portfolio = portfolio.rename(columns={"ticker": "Ticker", "shares": "Shares"})

    tradable, non_tradable = split_tradable(portfolio)

    if not non_tradable.empty:
        print("Not tradable via IBKR US-equity routing (skipped) -- manage these manually elsewhere:")
        print(non_tradable[["Ticker", "weight"]].to_string(index=False))
        print()

    try:
        client = get_trading_client()
    except ModuleNotFoundError:
        print("Error: the `ib-async` package isn't installed. Run: pip install -e \".[broker]\"", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        current_positions = get_current_positions(client)
        orders = compute_rebalance_orders(tradable, current_positions)

        if not orders:
            print(f"Run #{run_id}: account already matches the target portfolio. No orders needed.")
            return 0

        print(f"Run #{run_id}: {len(orders)} order(s) to sync the paper account to the target portfolio:")
        for order in orders:
            print(f"  {order.side.upper():4s} {order.qty:>12.4f}  {order.ticker}")

        if not args.execute:
            print("\nDry run only -- no orders submitted. Pass --execute to place them.")
            return 0

        submit_orders(client, orders)
        print(f"\nSubmitted {len(orders)} order(s) to IBKR paper trading.")
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
