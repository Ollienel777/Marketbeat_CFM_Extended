import argparse
import sys
from datetime import datetime
from pathlib import Path

from raam.backtest import compute_metrics, get_benchmark_equity_curve, run_backtest
from raam.config import RaamConfig
from raam.history import DEFAULT_DB_PATH, record_backtest_run


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="raam-backtest", description="Walk-forward backtest the RAAM strategy.")
    parser.add_argument("--tickers", required=True, help="Path to a CSV file of candidate tickers.")
    parser.add_argument("--start", required=True, help="Backtest start date (YYYY-MM-DD).")
    parser.add_argument("--end", required=True, help="Backtest end date (YYYY-MM-DD).")
    parser.add_argument("--budget", type=float, default=1_000_000, help="Initial budget in CAD.")
    parser.add_argument("--freq", default="ME", help="Rebalance frequency (pandas resample alias, e.g. ME=monthly, W=weekly).")
    parser.add_argument("--benchmark", default="SPY", help="Buy-and-hold benchmark ticker to compare against.")
    parser.add_argument("--out", default="backtest_results", help="Directory to write the equity curve CSV to.")
    parser.add_argument("--label", default=None, help="Tag this run (e.g. 'v1-baseline', 'v2-ewma-vol') for later comparison.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite history DB path to record this backtest into.")
    parser.add_argument("--no-record", action="store_true", help="Skip recording this backtest to the history DB.")
    return parser.parse_args(argv)


def _print_metrics(label: str, metrics: dict):
    if not metrics:
        print(f"{label}: not enough data to compute metrics.")
        return
    print(
        f"{label}: CAGR {metrics['cagr']:+.2%}  Vol {metrics['annualized_vol']:.2%}  "
        f"Sharpe {metrics['sharpe']:.2f}  MaxDD {metrics['max_drawdown']:.2%}  "
        f"PositiveMonths {metrics['pct_positive_months']:.0%}"
    )


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    cfg = RaamConfig(initial_budget_cad=args.budget)
    result = run_backtest(args.tickers, args.start, args.end, cfg, freq=args.freq)
    equity_curve = result["equity_curve"]

    if equity_curve.empty:
        print("Backtest produced no equity curve (no usable price data for this universe/window).", file=sys.stderr)
        return 1

    print(f"Ran {len(result['rebalance_log'])} rebalance(s) from {args.start} to {args.end}.")
    total_fees = sum(r["fees_cad"] for r in result["rebalance_log"])
    print(f"Total fees paid (CAD): {total_fees:,.2f}")

    strategy_metrics = compute_metrics(equity_curve)
    _print_metrics("Strategy ", strategy_metrics)

    benchmark_curve = get_benchmark_equity_curve(args.benchmark, args.start, args.end, args.budget)
    benchmark_metrics = {}
    if not benchmark_curve.empty:
        benchmark_metrics = compute_metrics(benchmark_curve)
        _print_metrics(f"{args.benchmark} (buy & hold)", benchmark_metrics)
    else:
        print(f"Could not fetch benchmark data for {args.benchmark}.")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    curve_path = out_dir / f"equity_curve_{args.start}_{args.end}.csv"

    out_df = equity_curve.rename("strategy_cad").to_frame()
    if not benchmark_curve.empty:
        out_df[f"{args.benchmark}_cad"] = benchmark_curve.reindex(out_df.index, method="ffill")
    out_df.to_csv(curve_path)
    print(f"Wrote equity curve to {curve_path}")

    if not args.no_record:
        backtest_id = record_backtest_run(
            db_path=args.db,
            run_at=datetime.now().isoformat(timespec="seconds"),
            label=args.label,
            tickers_path=args.tickers,
            start_date=args.start,
            end_date=args.end,
            budget_cad=args.budget,
            freq=args.freq,
            benchmark_ticker=args.benchmark,
            total_fees_cad=total_fees,
            strategy_metrics=strategy_metrics,
            benchmark_metrics=benchmark_metrics,
            equity_curve=equity_curve,
            benchmark_curve=benchmark_curve,
        )
        label_note = f" (label: {args.label})" if args.label else ""
        print(f"Recorded backtest #{backtest_id}{label_note} to {args.db}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
