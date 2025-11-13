import json
import os

from typing import Dict, Iterable, Tuple

import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(page_title="IGFX-Bot Dashboard", layout="wide")
st.title("📈 IGFX-Bot — Monitoring Dashboard")


@st.cache_data(show_spinner=False)
def load_backtest_metrics(path: str) -> dict:
    """Load a JSON metrics file if it exists."""

    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(show_spinner=False)
def load_historical_trades(path: str) -> pd.DataFrame:
    """Load a CSV file with historical trades."""

    if not os.path.exists(path):
        return pd.DataFrame()

    df = pd.read_csv(path, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    return df


def _pg_connection_kwargs() -> Dict[str, object]:
    """Collect TimescaleDB connection kwargs from the environment."""

    dsn = os.getenv("PG_DSN")
    if dsn:
        return {"dsn": dsn}

    host = os.getenv("PGHOST")
    if not host:
        return {}

    params = {
        "host": host,
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER"),
        "password": os.getenv("PGPASSWORD"),
        "dbname": os.getenv("PGDATABASE"),
    }

    # Remove empty values because psycopg2 does not like None strings.
    return {k: v for k, v in params.items() if v}


@st.cache_data(show_spinner=False)
def load_timescale_trades(conn_items: Iterable[Tuple[str, object]]) -> pd.DataFrame:
    """Load trades from the TimescaleDB `trades` table if configured."""

    if not conn_items:
        return pd.DataFrame()

    conn_kwargs = dict(conn_items)

    query = """
        SELECT
            id AS trade_id,
            ts AS timestamp,
            symbol,
            side,
            size,
            entry AS entry_price,
            sl,
            tp,
            deal_ref,
            raw
        FROM trades
        ORDER BY timestamp;
    """

    with psycopg2.connect(**conn_kwargs) as conn:
        df = pd.read_sql_query(query, conn, parse_dates=["timestamp"])

    if "raw" in df.columns:
        # Normalize JSON payload if possible; on some drivers jsonb returns str.
        df["raw"] = df["raw"].apply(
            lambda value: json.loads(value) if isinstance(value, str) else value
        )

        def _extract_pnl(raw_payload):
            if not isinstance(raw_payload, dict):
                return None
            candidates = (
                "profitAndLoss",
                "profitAndLossAmount",
                "pnl",
                "PnL",
            )
            for key in candidates:
                if key in raw_payload and raw_payload[key] is not None:
                    pnl_value = raw_payload[key]
                    if isinstance(pnl_value, dict) and "value" in pnl_value:
                        pnl_value = pnl_value["value"]
                    try:
                        return float(pnl_value)
                    except (TypeError, ValueError):
                        continue
            return None

        df["pnl"] = df.get("pnl")
        df.loc[df["pnl"].isna(), "pnl"] = df.loc[df["pnl"].isna(), "raw"].apply(
            _extract_pnl
        )

        def _extract_exit_ts(raw_payload):
            if not isinstance(raw_payload, dict):
                return None
            for key in ("closeTime", "closedTime", "exitTime"):
                if key in raw_payload and raw_payload[key]:
                    return raw_payload[key]
            return None

        exit_ts = df["raw"].apply(_extract_exit_ts)
        if exit_ts.notna().any():
            exit_ts = pd.to_datetime(exit_ts, errors="coerce")
            df.loc[exit_ts.notna(), "exit_timestamp"] = exit_ts[exit_ts.notna()]
            if "exit_timestamp" in df.columns:
                df.loc[exit_ts.notna(), "duration_min"] = (
                    (df.loc[exit_ts.notna(), "exit_timestamp"] - df.loc[exit_ts.notna(), "timestamp"])
                    .dt.total_seconds()
                    .div(60)
                )

    df.sort_values("timestamp", inplace=True)
    return df


metrics_path = os.path.join("samples", "sample_backtest_report.json")
trades_path = os.path.join("samples", "historical_trades.csv")

metrics = load_backtest_metrics(metrics_path)

conn_kwargs = _pg_connection_kwargs()
data_sources = ["Sample CSV"]
if conn_kwargs:
    data_sources.append("TimescaleDB (live)")

st.sidebar.header("Data Source")
selected_source = st.sidebar.selectbox("Trades", data_sources)

load_error = None
if selected_source == "TimescaleDB (live)":
    try:
        trades = load_timescale_trades(tuple(sorted(conn_kwargs.items())))
    except Exception as exc:  # pragma: no cover - surfaced to UI
        trades = pd.DataFrame()
        load_error = str(exc)
else:
    trades = load_historical_trades(trades_path)

st.markdown(
    """
This dashboard surfaces sample analytics for IGFX-Bot. Replace the sample files in the
`samples/` directory with your own exports (CSV/JSON) or wire the loaders to your TimescaleDB
instance for live monitoring.
"""
)

if load_error:
    st.sidebar.error(f"Unable to load trades from TimescaleDB: {load_error}")

st.sidebar.header("Filters")

if not trades.empty:
    available_symbols = sorted(trades["symbol"].unique())
    selected_symbols = st.sidebar.multiselect(
        "Symbols", options=available_symbols, default=available_symbols
    )

    available_sides = sorted(trades["side"].unique())
    selected_sides = st.sidebar.multiselect(
        "Sides", options=available_sides, default=available_sides
    )

    min_date = trades["timestamp"].min().date()
    max_date = trades["timestamp"].max().date()
    selected_date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
    else:
        start_date = end_date = selected_date_range

    filtered_trades = trades[
        trades["symbol"].isin(selected_symbols)
        & trades["side"].isin(selected_sides)
        & trades["timestamp"].dt.date.between(start_date, end_date)
    ]
else:
    st.sidebar.info("Add a CSV file with historical trades to populate this dashboard.")
    filtered_trades = trades


st.header("Performance Overview")

if metrics:
    metrics_section = metrics.get("metrics", {})
    metrics_cols = st.columns(4)
    metrics_cols[0].metric("Final Value", f"${metrics_section.get('final_value', 0):,.0f}")
    metrics_cols[1].metric("Return", f"{metrics_section.get('return_pct', 0):.2f}%")
    metrics_cols[2].metric("Win Rate", f"{metrics_section.get('win_rate', 0) * 100:.1f}%")
    metrics_cols[3].metric("Sharpe Ratio", f"{metrics_section.get('sharpe', 0):.2f}")

    st.caption(
        f"Strategy: {metrics.get('strategy')} — Symbol: {metrics.get('symbol')} — Timeframe: {metrics.get('timeframe')}"
    )
else:
    st.info("No backtest metrics found. Drop a JSON report into `samples/sample_backtest_report.json`.")


st.subheader("Trade Statistics")

if not filtered_trades.empty:
    total_trades = len(filtered_trades)
    pnl_available = "pnl" in filtered_trades.columns and pd.api.types.is_numeric_dtype(
        filtered_trades["pnl"]
    )
    duration_available = "duration_min" in filtered_trades.columns and pd.api.types.is_numeric_dtype(
        filtered_trades["duration_min"]
    )

    stats_cols = st.columns(5)
    stats_cols[0].metric("Trades", f"{total_trades}")

    if pnl_available and filtered_trades["pnl"].notna().any():
        pnl_series = filtered_trades["pnl"].fillna(0)
        winning_trades = pnl_series[pnl_series > 0]
        win_pct = (len(winning_trades) / total_trades) * 100 if total_trades else 0
        stats_cols[1].metric("Win %", f"{win_pct:.1f}%")
        stats_cols[2].metric("Avg. PnL", f"${pnl_series.mean():,.2f}")
        stats_cols[3].metric("Total PnL", f"${pnl_series.sum():,.2f}")
    else:
        stats_cols[1].metric("Win %", "N/A")
        stats_cols[2].metric("Avg. PnL", "N/A")
        stats_cols[3].metric("Total PnL", "N/A")

    if duration_available and filtered_trades["duration_min"].notna().any():
        stats_cols[4].metric(
            "Avg. Duration", f"{filtered_trades['duration_min'].mean():.1f} min"
        )
    else:
        stats_cols[4].metric("Avg. Duration", "N/A")

    if pnl_available and filtered_trades["pnl"].notna().any():
        best_trade = filtered_trades.loc[filtered_trades["pnl"].idxmax()]
        worst_trade = filtered_trades.loc[filtered_trades["pnl"].idxmin()]
        st.markdown(
            f"**Best Trade:** {best_trade['symbol']} {best_trade['side']} PnL ${best_trade['pnl']:,.2f} | "
            f"**Worst Trade:** {worst_trade['symbol']} {worst_trade['side']} PnL ${worst_trade['pnl']:,.2f}"
        )
    else:
        st.info(
            "PnL metrics are hidden because the data source does not include realized profit/loss yet."
        )

    if pnl_available and filtered_trades["pnl"].notna().any():
        pnl_chart = filtered_trades.copy()
        pnl_chart["cum_pnl"] = pnl_chart["pnl"].fillna(0).cumsum()
        pnl_chart.set_index("timestamp", inplace=True)

        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.area_chart(pnl_chart["cum_pnl"], use_container_width=True)
        with chart_col2:
            st.bar_chart(filtered_trades.set_index("timestamp")["pnl"], use_container_width=True)

    st.subheader("Historical Trades")
    display_trades = filtered_trades.set_index("timestamp")
    if "raw" in display_trades.columns:
        display_trades = display_trades.drop(columns=["raw"])
    st.dataframe(
        display_trades,
        use_container_width=True,
    )
else:
    st.warning("No trades match the current filters. Adjust the sidebar to see results.")


st.caption("Data shown is illustrative. Replace the sample files with your trading history for live analytics.")
