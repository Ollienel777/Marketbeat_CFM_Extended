import streamlit as st

from raam.broker import compute_rebalance_orders, split_tradable
from raam.dashboard_data import get_latest_run_id, get_run_overview
from raam.history import DEFAULT_DB_PATH, get_ticker_history, list_runs

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
orders = compute_rebalance_orders(tradable, current_positions={})
if orders:
    st.dataframe(
        [{"Ticker": o.ticker, "Side": o.side, "Qty": round(o.qty, 4)} for o in orders],
        use_container_width=True,
    )
if not non_tradable.empty:
    st.caption("Not tradable via IBKR US-equity routing (Canadian/.TO, futures, crypto, or cash):")
    st.dataframe(non_tradable[["Ticker", "Weight"]], use_container_width=True)

st.subheader("Ticker weight history")
ticker_query = st.text_input("Look up a ticker across all runs", value="")
if ticker_query:
    ticker_history = get_ticker_history(db_path, ticker_query)
    if ticker_history.empty:
        st.warning(f"No history found for {ticker_query.upper()}.")
    else:
        st.line_chart(ticker_history.set_index("run_at")["weight"])
        st.dataframe(ticker_history, use_container_width=True)
