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
            asset: Asset type to sync (ETH or USD)
            namespace: Dune namespace for tables
        """
        if asset not in ["ETH", "USD"]:
            raise ValueError("Asset must be either 'ETH' or 'USD'")

        self.asset = asset
        self.namespace = namespace
        self.contracts = CONTRACTS[asset]
        self.api_key = os.getenv("DUNE_API_KEY")
        if not self.api_key:
            raise ValueError("DUNE_API_KEY environment variable not set")

        self.base_url = "https://api.dune.com/api/v1"
        self.headers = {
            "X-DUNE-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

        # Initialize Web3 with multiple RPC URLs
        rpc_urls = os.getenv("ETH_RPC_URLS", "").split(",")
        if not rpc_urls or not rpc_urls[0]:
            raise ValueError("ETH_RPC_URLS environment variable not set")

        self.rpc_urls = [url.strip() for url in rpc_urls if url.strip()]
        self.w3 = Web3(Web3.HTTPProvider(random.choice(self.rpc_urls)))
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Ethereum node")

        # Get environment variables
        self.block_period = int(os.getenv("BLOCK_PERIOD", "1000"))
        self.block_retrieval_period = float(os.getenv("BLOCK_RETRIEVAL_PERIOD", "0.1"))

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
            bool: True if table was created successfully
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
                    return True
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
        """Sync historical data from contract creation to current block."""
        collector = BlockchainDataCollector(asset=self.asset)
        current_block = self.get_web3().eth.block_number

        print(
            f"{Fore.CYAN}Syncing historical data until block {current_block}{Style.RESET_ALL}"
        )

        # Collect data for each contract
        for contract_name in self.contracts:
            try:
                # Get contract creation block
                contract = self.contracts[contract_name]
                contract_address = contract["address"]
                creation_block = collector.get_contract_creation_block(contract_address)

                if creation_block is None:
                    print(
                        f"{Fore.RED}Could not find creation block for {contract_name}{Style.RESET_ALL}"
                    )
                    continue

                print(
                    f"{Fore.CYAN}Syncing {contract_name} from block {creation_block} to {current_block}{Style.RESET_ALL}"
                )

                # Create contract object
                w3 = collector.get_next_w3()
                contract_obj = w3.eth.contract(
                    address=Web3.to_checksum_address(contract_address),
                    abi=contract["abi"],
                )

                # Collect data
                df = collector.collect_contract_data(
                    contract_name, contract_obj, creation_block
                )

                # Create table if it doesn't exist
                if not self.create_table(contract_name, df):
                    # Insert data
                    self.insert_data(contract_name, df)

            except Exception as e:
                print(
                    f"{Fore.RED}Error syncing {contract_name}: {str(e)}{Style.RESET_ALL}"
                )
                continue

    def sync_daily_data(self) -> None:
        """Sync data for the current block."""
        collector = BlockchainDataCollector(asset=self.asset)
        current_block = self.get_web3().eth.block_number

        print(
            f"{Fore.CYAN}Syncing daily data at block {current_block}{Style.RESET_ALL}"
        )

        # Collect data for each contract
        for contract_name in self.contracts:
            try:
                # Get contract config
                contract = self.contracts[contract_name]
                contract_address = contract["address"]

                # Create contract object
                w3 = collector.get_next_w3()
                contract_obj = w3.eth.contract(
                    address=Web3.to_checksum_address(contract_address),
                    abi=contract["abi"],
                )

                # Collect data
                df = collector.collect_contract_data(
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
    parser = argparse.ArgumentParser(description="Sync data with Dune")
    parser.add_argument(
        "--asset",
        choices=["ETH", "USD"],
        default="ETH",
        help="Asset to sync data for (default: ETH)",
    )
    parser.add_argument(
        "--namespace",
        default="rangonomics",
        help="Dune namespace (default: rangonomics)",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Run daily sync at midnight",
    )

    args = parser.parse_args()

    try:
        sync = DuneSync(asset=args.asset, namespace=args.namespace)

        # Always run historical sync first

        if args.daily:
            # Run daily sync
            sync.schedule_daily_sync()

        else:
            sync.sync_historical_data()

    except Exception as e:
        print(f"{Fore.RED}Error: {str(e)}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
