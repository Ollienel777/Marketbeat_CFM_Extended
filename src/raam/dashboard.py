import streamlit as st

from raam.broker import compute_rebalance_orders, round_to_whole_shares, split_tradable
from raam.dashboard_data import get_latest_run_id, get_run_overview
from raam.history import DEFAULT_DB_PATH, get_ticker_history, list_account_snapshots, list_runs

st.set_page_config(page_title="RAAM Dashboard", layout="wide")
st.title("RAAM — Ranked Asset Allocation Model")

db_path = st.sidebar.text_input("History DB path", value=DEFAULT_DB_PATH)

runs = list_runs(db_path)
if runs.empty:
    st.info("No recorded runs yet. Run `raam --tickers <file>` first.")
    st.stop()

run_options = runs.sort_values("run_id", ascending=False)
run_labels = [f"#{row.run_id} — {row.run_at} ({row.selected_size} picks)" for row in run_options.itertuples()]
selected_label = st.sidebar.selectbox("Run", run_labels, index=0)
run_id = int(selected_label.split(" — ")[0].lstrip("#"))

overview = get_run_overview(db_path, run_id)
positions = overview["positions"]
scored_universe = overview["scored_universe"]

col1, col2, col3 = st.columns(3)
col1.metric("Selected stocks", len(positions))
col2.metric("Screened universe", len(scored_universe) if not scored_universe.empty else "—")
col3.metric("Portfolio value (CAD)", f"{positions['value'].sum():,.0f}")

st.subheader("Portfolio")
st.dataframe(positions.sort_values("weight", ascending=False), use_container_width=True)

st.subheader("Sector allocation")
sector_weights = overview["sector_weights"]
if not sector_weights.empty:
    st.bar_chart(sector_weights)
else:
    st.caption("No sector data for this run.")

if not scored_universe.empty:
    st.subheader("Risk vs. return (selected vs. screened universe)")
    selected_tickers = set(positions["ticker"])
    scored_universe = scored_universe.copy()
    scored_universe["Group"] = scored_universe["ticker"].apply(
        lambda t: "Selected" if t in selected_tickers else "Universe"
    )
    st.scatter_chart(scored_universe, x="volatility", y="momentum", color="Group")

    st.subheader("Factor comparison: selected vs. universe")
    st.dataframe(overview["factor_comparison"], use_container_width=True)

st.subheader("Rebalance preview (vs. an empty/zero account — dry run only)")
st.caption(
    "Shows what `raam-trade` would buy/sell to build this portfolio from scratch. "
    "Run `raam-trade` from a terminal to diff against your real IBKR paper account; "
    "this dashboard never submits orders."
)
tradable, non_tradable = split_tradable(
    positions.rename(columns={"ticker": "Ticker", "shares": "Shares", "weight": "Weight"})
)
orders = round_to_whole_shares(compute_rebalance_orders(tradable, current_positions={}))
if orders:
    st.caption("Whole shares only -- IBKR's API rejects fractional-share orders.")
    st.dataframe(
        [{"Ticker": o.ticker, "Side": o.side, "Qty": int(o.qty)} for o in orders],
        use_container_width=True,
    )
if not non_tradable.empty:
    st.caption("Not tradable via IBKR US-equity routing (Canadian/.TO, futures, crypto, or cash):")
    st.dataframe(non_tradable[["Ticker", "Weight"]], use_container_width=True)

st.subheader("Account equity / P&L over time")
st.caption(
    "Snapshots of your real IBKR paper account, taken automatically every time `raam-trade` "
    "connects. This reflects actual fills and price moves, not a theoretical valuation."
)
snapshots = list_account_snapshots(db_path)
if snapshots.empty:
    st.caption("No snapshots yet -- run `raam-trade` at least once to start tracking this.")
else:
    chart_data = snapshots.set_index("snapshot_at")[["net_liquidation"]].dropna()
    if not chart_data.empty:
        st.line_chart(chart_data)

    first_nl = snapshots["net_liquidation"].dropna()
    if len(first_nl) >= 1:
        latest = first_nl.iloc[-1]
        change = latest - first_nl.iloc[0]
        pct = (change / first_nl.iloc[0]) * 100 if first_nl.iloc[0] else 0.0
        c1, c2, c3 = st.columns(3)
        c1.metric("Net liquidation", f"${latest:,.2f}")
        c2.metric("Net change since first snapshot", f"${change:,.2f}", f"{pct:+.2f}%")
        c3.metric("Snapshots recorded", len(snapshots))
    st.dataframe(snapshots, use_container_width=True)

st.subheader("Ticker weight history")
ticker_query = st.text_input("Look up a ticker across all runs", value="")
if ticker_query:
    ticker_history = get_ticker_history(db_path, ticker_query)
    if ticker_history.empty:
        st.warning(f"No history found for {ticker_query.upper()}.")
    else:
        st.line_chart(ticker_history.set_index("run_at")["weight"])
        st.dataframe(ticker_history, use_container_width=True)
