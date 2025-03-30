import os
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from decimal import Decimal

# Constants for formatting
WAD = Decimal("1e18")  # 18 decimals for WAD format
RAY = Decimal("1e27")  # 27 decimals for RAY format
USD_DECIMALS = Decimal("1e8")  # 8 decimals for USD price


def format_wei(value: str) -> float:
    """Convert from Wei to ETH."""
    return float(Decimal(str(value)) / WAD)


def format_ray(value: str) -> float:
    """Convert from Ray to percentage."""
    return float(Decimal(str(value)) / RAY)


def format_usd(value: str) -> float:
    """Convert from USD decimals to USD."""
    return float(Decimal(str(value)) / USD_DECIMALS)


def load_data(data_dir: str = "data") -> dict:
    """Load all CSV files from the data directory."""
    data = {}
    for file in os.listdir(data_dir):
        if file.endswith(".csv"):
            contract_name = file.replace(".csv", "")
            df = pd.read_csv(os.path.join(data_dir, file))
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            data[contract_name] = df
    return data


def plot_total_debt(data: dict, asset: str):
    """Plot total debt over time."""
    if asset == "ETH":
        df = data["spectra_cdp"]
        value_col = "total_debt"
        title = "Total Debt (ETH)"
        y_label = "ETH"
        formatter = format_wei
    else:
        df = data["deusd_cdp"]
        value_col = "total_debt"
        title = "Total Debt (USD)"
        y_label = "USD"
        formatter = format_usd

    df["formatted_value"] = df[value_col].apply(formatter)

    fig = px.line(
        df,
        x="timestamp",
        y="formatted_value",
        title=title,
        labels={"formatted_value": y_label, "timestamp": "Time"},
    )

    st.plotly_chart(fig, use_container_width=True)


def plot_interest_rates(data: dict, asset: str):
    """Plot interest rates over time."""
    if asset == "ETH":
        df = data["lp_eth_pool"]
        title = "Interest Rates (ETH)"
    else:
        df = data["lp_usd_pool"]
        title = "Interest Rates (USD)"

    df["base_rate"] = df["base_interest_rate"].apply(format_ray)
    df["supply_rate"] = df["supply_rate"].apply(format_ray)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["base_rate"],
            name="Base Rate",
            line=dict(color="blue"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["supply_rate"],
            name="Supply Rate",
            line=dict(color="red"),
        )
    )

    fig.update_layout(
        title=title, xaxis_title="Time", yaxis_title="Rate (%)", hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)


def plot_liquidity(data: dict, asset: str):
    """Plot available and expected liquidity over time."""
    if asset == "ETH":
        df = data["lp_eth_pool"]
        title = "Liquidity (ETH)"
        y_label = "ETH"
        formatter = format_wei
    else:
        df = data["lp_usd_pool"]
        title = "Liquidity (USD)"
        y_label = "USD"
        formatter = format_usd

    df["available"] = df["available_liquidity"].apply(formatter)
    df["expected"] = df["expected_liquidity"].apply(formatter)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["available"],
            name="Available Liquidity",
            line=dict(color="green"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["expected"],
            name="Expected Liquidity",
            line=dict(color="blue"),
        )
    )

    fig.update_layout(
        title=title, xaxis_title="Time", yaxis_title=y_label, hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)


def plot_tvl(data: dict, asset: str):
    """Plot TVL over time."""
    if asset == "ETH":
        df = data["slp_eth"]
        title = "TVL (ETH)"
        y_label = "ETH"
        formatter = format_wei
    else:
        df = data["slp_usd"]
        title = "TVL (USD)"
        y_label = "USD"
        formatter = format_usd

    df["tvl"] = df["total_supply"].apply(formatter)

    fig = px.line(
        df,
        x="timestamp",
        y="tvl",
        title=title,
        labels={"tvl": y_label, "timestamp": "Time"},
    )

    st.plotly_chart(fig, use_container_width=True)


def main():
    st.set_page_config(page_title="Loop Protocol Dashboard", layout="wide")

    st.title("Loop Protocol Dashboard")

    # Asset selector
    asset = st.sidebar.selectbox("Select Asset", ["ETH", "USD"])

    # Load data
    data = load_data()

    # Display metrics
    st.header("Key Metrics")

    if asset == "ETH":
        cdp_data = data["spectra_cdp"]
        pool_data = data["lp_eth_pool"]
        slp_data = data["slp_eth"]
    else:
        cdp_data = data["deusd_cdp"]
        pool_data = data["lp_usd_pool"]
        slp_data = data["slp_usd"]

    # Latest values
    col1, col2, col3 = st.columns(3)

    with col1:
        latest_debt = (
            format_wei(cdp_data["total_debt"].iloc[-1])
            if asset == "ETH"
            else format_usd(cdp_data["total_debt"].iloc[-1])
        )
        st.metric("Total Debt", f"{latest_debt:,.2f} {asset}")

    with col2:
        latest_liquidity = (
            format_wei(pool_data["available_liquidity"].iloc[-1])
            if asset == "ETH"
            else format_usd(pool_data["available_liquidity"].iloc[-1])
        )
        st.metric("Available Liquidity", f"{latest_liquidity:,.2f} {asset}")

    with col3:
        latest_tvl = (
            format_wei(slp_data["total_supply"].iloc[-1])
            if asset == "ETH"
            else format_usd(slp_data["total_supply"].iloc[-1])
        )
        st.metric("TVL", f"{latest_tvl:,.2f} {asset}")

    # Plots
    st.header("Charts")

    # Total Debt
    plot_total_debt(data, asset)

    # Interest Rates
    plot_interest_rates(data, asset)

    # Liquidity
    plot_liquidity(data, asset)

    # TVL
    plot_tvl(data, asset)

    # Raw data table
    st.header("Raw Data")
    contract = st.selectbox("Select Contract", list(data.keys()))
    st.dataframe(data[contract])


if __name__ == "__main__":
    main()
