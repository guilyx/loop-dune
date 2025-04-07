import os
import time
import json
import requests
import pandas as pd
from datetime import datetime, time as dt_time
from typing import Dict, Any, Optional, List
from decimal import Decimal
from web3 import Web3
from colorama import Fore, Style, init
from dotenv import load_dotenv
import schedule
import argparse
import random

from loop_dune.config.contracts import CONTRACTS
from loop_dune.collector import BlockchainDataCollector

# Initialize colorama
init(autoreset=True)

# Load environment variables
load_dotenv()


class DuneSync:
    def __init__(self, asset: str = "ETH", namespace: str = "rangonomics"):
        """
        Initialize the Dune sync manager.

        Args:
            asset: Asset type to sync (ETH, USD, or BNB)
            namespace: Dune namespace for tables
        """
        if asset not in ["ETH", "USD", "BNB"]:
            raise ValueError("Asset must be either 'ETH', 'USD', or 'BNB'")

        self.asset = asset
        self.namespace = namespace
        self.contracts = CONTRACTS[asset]
        self.chain_id = int(
            self.contracts.get("chain_id", 1)
        )  # Default to Ethereum mainnet (1)
        self.api_key = os.getenv("DUNE_API_KEY")
        if not self.api_key:
            raise ValueError("DUNE_API_KEY environment variable not set")

        # Check for Etherscan API key
        self.etherscan_api_key = os.getenv("ETHERSCAN_API_KEY")
        if not self.etherscan_api_key:
            print(
                f"{Fore.YELLOW}Warning: ETHERSCAN_API_KEY not set. Some features may not work.{Style.RESET_ALL}"
            )

        self.base_url = "https://api.dune.com/api/v1"
        self.headers = {
            "X-DUNE-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

        # Initialize Web3 with multiple RPC URLs
        rpc_urls = os.getenv(f"{asset}_RPC_URLS", "").split(",")
        if not rpc_urls or not rpc_urls[0]:
            raise ValueError(f"{asset}_RPC_URLS environment variable not set")

        self.rpc_urls = [url.strip() for url in rpc_urls if url.strip()]
        self.w3 = Web3(Web3.HTTPProvider(random.choice(self.rpc_urls)))

        # Add PoA middleware for BSC and other PoA chains
        if self.chain_id in [56, 97]:  # BSC Mainnet and Testnet
            from web3.middleware import geth_poa_middleware

            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            print(
                f"{Fore.GREEN}Added PoA middleware for BSC (chain ID: {self.chain_id}){Style.RESET_ALL}"
            )

        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {asset} node")

        # Get environment variables
        self.block_period = int(os.getenv("BLOCK_PERIOD", "1000"))
        self.block_retrieval_period = float(os.getenv("BLOCK_RETRIEVAL_PERIOD", "0.1"))

        # Initialize the collector
        self.collector = BlockchainDataCollector(asset=self.asset)

    def get_web3(self) -> Web3:
        """Get a Web3 instance with a random RPC URL."""
        return Web3(Web3.HTTPProvider(random.choice(self.rpc_urls)))

    def create_table(self, contract_name: str, df: pd.DataFrame) -> bool:
        """
        Create a Dune table with the appropriate schema.

        Args:
            contract_name: Name of the contract
            df: DataFrame containing the data

        Returns:
            bool: True if table was created successfully, False if table already exists or error
        """
        # Prepare schema from DataFrame
        schema = []
        for col in df.columns:
            # Determine column type
            if col == "timestamp":
                col_type = "timestamp"
            elif df[col].dtype in ["int64", "float64"]:
                col_type = "double"
            else:
                col_type = "varchar"

            schema.append({"name": col, "type": col_type, "nullable": True})

        # Prepare request data
        data = {
            "table_name": f"{contract_name}_{self.asset.lower()}",
            "schema": schema,
            "description": f"Data for {contract_name} ({self.asset})",
            "is_private": False,
        }

        try:
            response = requests.post(
                f"{self.base_url}/table/create", headers=self.headers, json=data
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("success", False):
                    print(
                        f"{Fore.GREEN}Created table {data['table_name']}{Style.RESET_ALL}"
                    )
                    return True
                else:
                    print(
                        f"{Fore.YELLOW}Table {data['table_name']} already exists{Style.RESET_ALL}"
                    )
                    return False
            else:
                print(
                    f"{Fore.RED}Error creating table: {response.text}{Style.RESET_ALL}"
                )
                return False

        except Exception as e:
            print(f"{Fore.RED}Error creating table: {str(e)}{Style.RESET_ALL}")
            return False

    def insert_data(self, contract_name: str, df: pd.DataFrame) -> bool:
        """
        Insert data into a Dune table.

        Args:
            contract_name: Name of the contract
            df: DataFrame containing the data

        Returns:
            bool: True if data was inserted successfully
        """
        # Validate DataFrame is not empty
        if df.empty:
            print(
                f"{Fore.YELLOW}No data to insert for {contract_name}{Style.RESET_ALL}"
            )
            return False

        table_name = f"{contract_name}_{self.asset.lower()}"

        try:
            # Log each data point being inserted
            print(
                f"\n{Fore.CYAN}Inserting {len(df)} data points for {contract_name}:{Style.RESET_ALL}"
            )
            for _, row in df.iterrows():
                print(
                    f"{Fore.YELLOW}Block {row['block_number']} ({row['timestamp']}):{Style.RESET_ALL}"
                )
                for col in df.columns:
                    if col not in ["block_number", "timestamp"]:
                        print(f"  {col}: {row[col]}")

            # Convert DataFrame to CSV string
            csv_data = df.to_csv(index=False)

            response = requests.post(
                f"{self.base_url}/table/{self.namespace}/{table_name}/insert",
                headers={"X-DUNE-API-KEY": self.api_key, "Content-Type": "text/csv"},
                data=csv_data,
            )

            if response.status_code == 200:
                result = response.json()
                print(
                    f"{Fore.GREEN}Inserted {result['rows_written']} rows into {table_name}{Style.RESET_ALL}"
                )
                return True
            else:
                print(
                    f"{Fore.RED}Error inserting data: {response.text}{Style.RESET_ALL}"
                )
                return False

        except Exception as e:
            print(f"{Fore.RED}Error inserting data: {str(e)}{Style.RESET_ALL}")
            return False

    def sync_historical_data(self) -> None:
        """Sync historical data for all contracts."""
        print(f"\n{Fore.CYAN}Starting historical data sync{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")

        # Get current block from any Web3 instance
        current_block = self.w3.eth.block_number
        print(f"{Fore.YELLOW}Current block: {current_block}{Style.RESET_ALL}")

        # Get creation blocks for all contracts
        creation_blocks = self.collector.check_contract_creation_blocks()

        if not creation_blocks:
            print(f"{Fore.RED}No valid contracts found. Exiting.{Style.RESET_ALL}")
            return

        # Process each contract
        for contract_name, creation_block in creation_blocks.items():
            try:
                print(
                    f"\n{Fore.GREEN}Processing contract: {contract_name}{Style.RESET_ALL}"
                )
                print(f"{Fore.YELLOW}Creation block: {creation_block}{Style.RESET_ALL}")

                # Calculate the number of blocks to process in each chunk
                start_block = creation_block
                end_block = start_block

                while start_block < current_block:
                    print(
                        f"\n{Fore.CYAN}Processing blocks {start_block} to {end_block}{Style.RESET_ALL}"
                    )

                    # Collect data for this chunk
                    df = self.collector.collect_contract_data(
                        contract_name=contract_name,
                        contract=self.collector.get_contract(contract_name),
                        creation_block=start_block,
                        end_block=end_block,
                    )

                    if not df.empty:
                        # Insert this chunk of data
                        if not self.create_table(contract_name, df):
                            print(
                                f"{Fore.RED}Failed to create table, maybe it already exist. Let's insert {contract_name}{Style.RESET_ALL}"
                            )

                        success = self.insert_data(contract_name, df)
                        if not success:
                            print(
                                f"{Fore.RED}Failed to insert data for {contract_name}{Style.RESET_ALL}"
                            )
                            break
                    else:
                        print(
                            f"{Fore.YELLOW}No data to insert for {contract_name}{Style.RESET_ALL}"
                        )

                    # Update blocks for next chunk
                    start_block = end_block + self.block_period
                    end_block = start_block

                print(
                    f"{Fore.GREEN}Completed processing {contract_name}{Style.RESET_ALL}"
                )

            except Exception as e:
                print(
                    f"{Fore.RED}Error processing {contract_name}: {e}{Style.RESET_ALL}"
                )
                continue

        print(f"\n{Fore.GREEN}Historical data sync completed!{Style.RESET_ALL}")

    def sync_daily_data(self) -> None:
        """Sync data for the current block."""
        current_block = self.w3.eth.block_number

        print(
            f"{Fore.CYAN}Syncing daily data at block {current_block}{Style.RESET_ALL}"
        )

        # Collect data for each contract
        for contract_name in self.contracts:
            try:
                # Get contract object
                contract_obj = self.collector.get_contract(contract_name)

                # Collect data
                df = self.collector.collect_contract_data(
                    contract_name, contract_obj, current_block
                )

                # Insert data
                self.insert_data(contract_name, df)

            except Exception as e:
                print(
                    f"{Fore.RED}Error syncing {contract_name}: {str(e)}{Style.RESET_ALL}"
                )
                continue

    def schedule_daily_sync(self) -> None:
        """Schedule daily sync at midnight."""
        schedule.every().day.at("00:00").do(self.sync_daily_data)

        print(f"{Fore.CYAN}Scheduled daily sync at 00:00{Style.RESET_ALL}")

        while True:
            schedule.run_pending()
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="Sync blockchain data to Dune Analytics"
    )
    parser.add_argument(
        "--asset",
        choices=["ETH", "USD", "BNB"],
        default="ETH",
        help="Asset to sync data for (default: ETH)",
    )
    parser.add_argument(
        "--namespace",
        default="rangonomics",
        help="Dune namespace for tables (default: rangonomics)",
    )
    parser.add_argument(
        "--mode",
        choices=["historical", "daily", "both"],
        default="both",
        help="Sync mode (default: both)",
    )
    args = parser.parse_args()

    sync = DuneSync(asset=args.asset, namespace=args.namespace)

    if args.mode in ["historical", "both"]:
        sync.sync_historical_data()

    if args.mode in ["daily", "both"]:
        sync.sync_daily_data()


if __name__ == "__main__":
    main()
