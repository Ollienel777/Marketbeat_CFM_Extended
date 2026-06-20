import argparse
import sys
from datetime import datetime

from raam.broker import (
    compute_rebalance_orders,
    get_account_summary,
    get_current_positions,
    get_trading_client,
    round_to_whole_shares,
    split_tradable,
    submit_orders,
)
from raam.history import DEFAULT_DB_PATH, get_run_positions, list_runs, record_account_snapshot


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="raam-trade", description="Sync an IBKR paper-trading account to a recorded RAAM run."
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite history DB path.")
    parser.add_argument("--run-id", type=int, default=None, help="Run to sync to. Defaults to the latest run.")
    parser.add_argument("--execute", action="store_true", help="Actually submit orders. Without this, it's a dry run.")
    parser.add_argument(
        "--no-snapshot", action="store_true", help="Skip recording the account's equity/P&L snapshot."
    )
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
        if not args.no_snapshot:
            summary = get_account_summary(client)
            record_account_snapshot(
                db_path=args.db,
                snapshot_at=datetime.now().isoformat(timespec="seconds"),
                account_id=summary["account_id"],
                net_liquidation=summary["net_liquidation"],
                cash_balance=summary["cash_balance"],
                gross_position_value=summary["gross_position_value"],
                unrealized_pnl=summary["unrealized_pnl"],
                realized_pnl=summary["realized_pnl"],
            )
            if summary["net_liquidation"] is not None:
                print(
                    f"Account snapshot: net liquidation ${summary['net_liquidation']:,.2f}, "
                    f"unrealized P&L ${summary['unrealized_pnl'] or 0:,.2f}, "
                    f"realized P&L ${summary['realized_pnl'] or 0:,.2f}"
                )
            print()

        current_positions = get_current_positions(client)
        orders = compute_rebalance_orders(tradable, current_positions)

        # IBKR's API rejects fractional-share orders, so what we display must match
        # what we'd actually submit -- round before printing, not just before submitting.
        whole_orders = round_to_whole_shares(orders)
        skipped = len(orders) - len(whole_orders)

        if not whole_orders:
            print(f"Run #{run_id}: account already matches the target portfolio (within a whole share). No orders needed.")
            return 0

        print(f"Run #{run_id}: {len(whole_orders)} whole-share order(s) to sync the paper account to the target portfolio:")
        for order in whole_orders:
            print(f"  {order.side.upper():4s} {order.qty:>12.0f}  {order.ticker}")
        if skipped:
            print(f"  ({skipped} order(s) rounded down to 0 shares and were skipped -- target weight was too small relative to price)")

        if not args.execute:
            print("\nDry run only -- no orders submitted. Pass --execute to place them.")
            return 0

        submit_orders(client, whole_orders)
        print(f"\nSubmitted {len(whole_orders)} order(s) to IBKR paper trading.")
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
