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
from loop_dune.config.contracts import CONTRACTS, load_abi

# Load environment variables
load_dotenv()

# Initialize Web3
rpc_urls = os.getenv("ETH_RPC_URLS", "").split(",")
if not rpc_urls or not rpc_urls[0]:
    raise ValueError("ETH_RPC_URLS environment variable not set")
w3 = Web3(Web3.HTTPProvider(rpc_urls[0].strip()))


def save_contract_config(contract_data: Dict[str, Any]) -> None:
    """Save contract configuration to config/contracts.json"""
    config_path = Path("config/contracts.json")
    config_path.parent.mkdir(exist_ok=True)

    if config_path.exists():
        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        config = {"ETH": {}, "USD": {}}

    asset = contract_data["asset"]
    name = contract_data["name"]

    config[asset][name] = {
        "address": contract_data["address"],
        "abi": contract_data["abi"],
        "functions": contract_data["functions"],
    }

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def load_existing_config() -> Dict[str, Dict[str, Any]]:
    """Load existing contract configuration or create from CONTRACTS"""
    config_path = Path("config/contracts.json")

    if config_path.exists():
        with open(config_path, "r") as f:
            return json.load(f)

    # If no config exists, create from CONTRACTS
    config = {"ETH": {}, "USD": {}}

    for asset in ["ETH", "USD"]:
        for contract_name, contract_data in CONTRACTS[asset].items():
            # Load ABI from file
            abi = load_abi(contract_name, asset)

            # Convert functions_to_track to the format used in the dashboard
            functions = [
                {
                    "name": func["name"],
                    "params": func["params"],
                    "column": func["column_names"][0],  # Using first column name
                }
                for func in contract_data["functions_to_track"]
            ]

            config[asset][contract_name] = {
                "address": contract_data["address"],
                "abi": abi,
                "functions": functions,
            }

    # Save the initial config
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    return config


def fetch_contract_data(
    contract_data: Dict[str, Any],
    start_block: int,
    end_block: Optional[int] = None,
    step: int = 1,
    rate: float = 0.1,
) -> pd.DataFrame:
    """Fetch data for a contract"""
    collector = BlockchainDataCollector(asset=contract_data["asset"])

    # Create contract object
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_data["address"]),
        abi=contract_data["abi"],
    )

    if end_block is None:
        end_block = start_block

    return collector.collect_contract_data(
        contract_data["name"], contract, start_block, end_block, step, rate
    )


def main():
    st.set_page_config(page_title="Loop Dune Dashboard", layout="wide")
    st.title("Loop Dune Dashboard")

    # Load existing configuration
    config = load_existing_config()

    # Sidebar for navigation
    page = st.sidebar.radio(
        "Navigation", ["Contract Management", "Data Collection", "Dune Integration"]
    )

    if page == "Contract Management":
        st.header("Contract Management")

        # Display existing contracts
        st.subheader("Existing Contracts")

        for asset in ["ETH", "USD"]:
            if asset in config and config[asset]:
                st.write(f"### {asset} Contracts")
                for contract_name, contract_data in config[asset].items():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{contract_name}**")
                        st.write(f"Address: `{contract_data['address']}`")
                        st.write(f"Functions: {len(contract_data['functions'])}")
                    with col2:
                        if st.checkbox("Select", key=f"select_{asset}_{contract_name}"):
                            st.write("Selected for data collection")

        # Add new contract form
        st.subheader("Add New Contract")
        with st.form("contract_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Contract Name")
                address = st.text_input("Contract Address")
                asset = st.selectbox("Asset Type", ["ETH", "USD"])

            with col2:
                abi = st.text_area("Contract ABI (JSON)")
                try:
                    abi = json.loads(abi) if abi else []
                except json.JSONDecodeError:
                    st.error("Invalid ABI JSON")
                    abi = []

            # Function configuration
            st.subheader("Functions to Track")
            functions = []

            num_functions = st.number_input("Number of Functions", min_value=1, value=1)

            for i in range(num_functions):
                with st.expander(f"Function {i+1}"):
                    func_name = st.text_input(f"Function Name {i+1}")
                    func_params = st.text_input(f"Parameters (comma-separated) {i+1}")
                    column_name = st.text_input(f"Column Name {i+1}")

                    if func_name and column_name:
                        functions.append(
                            {
                                "name": func_name,
                                "params": (
                                    [p.strip() for p in func_params.split(",")]
                                    if func_params
                                    else []
                                ),
                                "column": column_name,
                            }
                        )

            if st.form_submit_button("Add Contract"):
                if name and address and abi and functions:
                    contract_data = {
                        "name": name,
                        "address": address,
                        "asset": asset,
                        "abi": abi,
                        "functions": functions,
                    }
                    save_contract_config(contract_data)
                    st.success(f"Contract {name} added successfully!")
                    st.experimental_rerun()  # Refresh to show new contract
                else:
                    st.error("Please fill in all required fields")

    elif page == "Data Collection":
        st.header("Data Collection")

        # Contract selection
        asset = st.selectbox("Select Asset", ["ETH", "USD"])
        if asset in config and config[asset]:
            contract_name = st.selectbox("Select Contract", list(config[asset].keys()))
            contract_data = config[asset][contract_name]

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
                        {"name": contract_name, **contract_data},
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
        if asset in config and config[asset]:
            contract_name = st.selectbox("Select Contract", list(config[asset].keys()))
            contract_data = config[asset][contract_name]

            # Load CSV data
            csv_path = Path("data") / f"{contract_name}.csv"
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                st.success(f"Loaded {len(df)} data points from CSV")

                # Display data preview
                st.subheader("Data Preview")
                st.dataframe(df.head())

                # Dune integration options
                st.subheader("Dune Integration")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Create Table"):
                        dune_sync = DuneSync(asset=asset)
                        if dune_sync.create_table(contract_name, df):
                            st.success("Table created successfully!")
                        else:
                            st.error("Failed to create table")

                with col2:
                    if st.button("Insert Data"):
                        dune_sync = DuneSync(asset=asset)
                        if dune_sync.insert_data(contract_name, df):
                            st.success("Data inserted successfully!")
                        else:
                            st.error("Failed to insert data")
            else:
                st.error(
                    f"No CSV file found for {contract_name}. Please collect data first."
                )


if __name__ == "__main__":
    main()
