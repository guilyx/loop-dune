import os
import json
import streamlit as st
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Optional
from web3 import Web3
from dotenv import load_dotenv

from loop_dune.collector import BlockchainDataCollector
from loop_dune.sync import DuneSync
from loop_dune.config.contracts import CONTRACTS

# Load environment variables
load_dotenv()

# Initialize Web3
rpc_urls = os.getenv("ETH_RPC_URLS", "").split(",")
if not rpc_urls or not rpc_urls[0]:
    raise ValueError("ETH_RPC_URLS environment variable not set")
w3 = Web3(Web3.HTTPProvider(rpc_urls[0].strip()))


def fetch_contract_data(
    contract_name: str,
    asset: str,
    start_block: int,
    end_block: Optional[int] = None,
    step: int = 1,
    rate: float = 0.1,
) -> pd.DataFrame:
    """Fetch data for a contract"""
    collector = BlockchainDataCollector(asset=asset)
    contract_data = CONTRACTS[asset][contract_name]

    # Create contract object
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_data["address"]),
        abi=contract_data["abi"],
    )

    if end_block is None:
        end_block = start_block

    return collector.collect_contract_data(
        contract_name, contract, start_block, end_block, step, rate
    )


def main():
    st.set_page_config(page_title="Loop Dune Dashboard", layout="wide")
    st.title("Loop Dune Dashboard")

    # Sidebar for navigation
    page = st.sidebar.radio(
        "Navigation", ["Contract Management", "Data Collection", "Dune Integration"]
    )

    if page == "Contract Management":
        st.header("Contract Management")

        # Display existing contracts
        st.subheader("Existing Contracts")

        for asset in ["ETH", "USD"]:
            if asset in CONTRACTS and CONTRACTS[asset]:
                st.write(f"### {asset} Contracts")
                for contract_name, contract_data in CONTRACTS[asset].items():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{contract_name}**")
                        st.write(f"Address: `{contract_data['address']}`")
                        st.write(
                            f"Functions: {len(contract_data['functions_to_track'])}"
                        )
                    with col2:
                        if st.checkbox("Select", key=f"select_{asset}_{contract_name}"):
                            st.write("Selected for data collection")

        # Note about contract configuration
        st.info(
            """
        Contract configurations are managed in `loop_dune/config/contracts.py`.
        To add or modify contracts, please update the CONTRACTS dictionary in that file.
        """
        )

    elif page == "Data Collection":
        st.header("Data Collection")

        # Contract selection
        asset = st.selectbox("Select Asset", ["ETH", "USD"])
        if asset in CONTRACTS and CONTRACTS[asset]:
            contract_name = st.selectbox(
                "Select Contract", list(CONTRACTS[asset].keys())
            )
            contract_data = CONTRACTS[asset][contract_name]

            # Data collection parameters
            col1, col2 = st.columns(2)
            with col1:
                start_block = st.number_input("Start Block", min_value=0)
                end_block = st.number_input(
                    "End Block (optional)", min_value=0, value=start_block
                )
                step = st.number_input("Block Step", min_value=1, value=1)

            with col2:
                rate = st.number_input(
                    "Fetch Rate (seconds)", min_value=0.1, value=0.1, step=0.1
                )

            if st.button("Fetch Data"):
                with st.spinner("Fetching data..."):
                    df = fetch_contract_data(
                        contract_name,
                        asset,
                        start_block,
                        end_block,
                        step,
                        rate,
                    )

                    if not df.empty:
                        st.success(f"Successfully fetched {len(df)} data points")
                        st.dataframe(df)

                        # Save to CSV
                        data_dir = Path("data")
                        data_dir.mkdir(exist_ok=True)
                        csv_path = data_dir / f"{contract_name}.csv"
                        df.to_csv(csv_path, index=False)
                        st.success(f"Data saved to {csv_path}")
                    else:
                        st.warning("No data was fetched")

    else:  # Dune Integration
        st.header("Dune Integration")

        # Contract selection
        asset = st.selectbox("Select Asset", ["ETH", "USD"])
        if asset in CONTRACTS and CONTRACTS[asset]:
            contract_name = st.selectbox(
                "Select Contract", list(CONTRACTS[asset].keys())
            )
            contract_data = CONTRACTS[asset][contract_name]

            # Display contract info
            st.write(f"**Contract:** {contract_name}")
            st.write(f"**Address:** `{contract_data['address']}`")
            st.write(f"**Functions:** {len(contract_data['functions_to_track'])}")

            # Data file selection
            data_dir = Path("data")
            if data_dir.exists():
                csv_files = list(data_dir.glob("*.csv"))
                if csv_files:
                    selected_file = st.selectbox(
                        "Select Data File",
                        [f.name for f in csv_files],
                        format_func=lambda x: x.replace(".csv", ""),
                    )

                    if selected_file:
                        df = pd.read_csv(data_dir / selected_file)
                        st.write("### Data Preview")
                        st.dataframe(df)

                        if st.button("Upload to Dune"):
                            sync = DuneSync(asset=asset)
                            if sync.create_table(contract_name, df):
                                if sync.insert_data(contract_name, df):
                                    st.success("Data uploaded successfully!")
                                else:
                                    st.error("Failed to insert data")
                            else:
                                st.error("Failed to create table")
                else:
                    st.warning("No data files found. Please collect data first.")
            else:
                st.warning("Data directory not found. Please collect data first.")


if __name__ == "__main__":
    main()
