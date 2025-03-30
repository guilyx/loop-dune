import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import argparse

import pandas as pd
from colorama import Fore, Style, init
from dotenv import load_dotenv
from tqdm import tqdm
from web3 import Web3
from web3.contract import Contract
import requests
from urllib.parse import urlencode

from loop_dune.config.contracts import CONTRACTS

# Initialize colorama for cross-platform color support
init()

# Load environment variables
load_dotenv()


class BlockchainDataCollector:
    def __init__(self, asset: str = "ETH"):
        """
        Initialize the data collector.

        Args:
            asset: Asset type to collect data for (ETH or USD)
        """
        if asset not in ["ETH", "USD"]:
            raise ValueError("Asset must be either 'ETH' or 'USD'")

        self.asset = asset
        self.contracts = CONTRACTS[asset]

        # Initialize multiple Web3 instances for different RPCs
        rpc_urls = os.getenv("ETH_RPC_URLS", "").split(",")
        if not rpc_urls or not rpc_urls[0]:
            raise ValueError("No RPC URLs provided in ETH_RPC_URLS")

        self.w3_instances = [Web3(Web3.HTTPProvider(url)) for url in rpc_urls]
        self.current_w3_index = 0
        self.blocks_period = int(os.getenv("BLOCKS_PERIOD", "100"))
        self.block_retrieval_period = float(os.getenv("BLOCK_RETRIEVAL_PERIOD", "60"))
        self.data_dir = os.getenv("DATA_DIR", "data")
        os.makedirs(self.data_dir, exist_ok=True)

        print(
            f"\n{Fore.CYAN}Initialized collector with {len(self.w3_instances)} RPC endpoints{Style.RESET_ALL}"
        )
        print(f"{Fore.CYAN}Blocks period: {self.blocks_period}{Style.RESET_ALL}")
        print(
            f"{Fore.CYAN}Block retrieval period: {self.block_retrieval_period}s{Style.RESET_ALL}"
        )
        print(f"{Fore.CYAN}Data directory: {self.data_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Asset: {asset}{Style.RESET_ALL}\n")

    def get_next_w3(self) -> Web3:
        """Get the next Web3 instance in a round-robin fashion."""
        w3 = self.w3_instances[self.current_w3_index]
        self.current_w3_index = (self.current_w3_index + 1) % len(self.w3_instances)
        return w3

    def get_contract_creation_block(self, contract_address: str) -> int:
        """Get the block number where the contract was created using Etherscan API."""
        # Get API key from environment
        api_key = os.getenv("ETHERSCAN_API_KEY")
        if not api_key:
            raise ValueError("ETHERSCAN_API_KEY environment variable not set")

        # Prepare API request parameters
        params = {
            "chainid": 1,
            "module": "contract",
            "action": "getcontractcreation",
            "contractaddresses": contract_address,
            "apikey": api_key,
        }

        # Make API request
        base_url = "https://api.etherscan.io/v2/api"
        url = f"{base_url}?{urlencode(params)}"

        print(
            f"{Fore.YELLOW}Fetching contract creation block from Etherscan...{Style.RESET_ALL}"
        )

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            if data["status"] != "1":
                raise ValueError(f"Etherscan API error: {data['message']}")

            if not data["result"]:
                raise ValueError(
                    f"No creation data found for contract {contract_address}"
                )

            # Get the first (and only) result
            result = data["result"][0]
            creation_block = int(result["blockNumber"])

            print(
                f"{Fore.GREEN}Found contract creation block: {creation_block}{Style.RESET_ALL}"
            )
            return creation_block

        except requests.exceptions.RequestException as e:
            print(f"{Fore.RED}Error fetching from Etherscan API: {e}{Style.RESET_ALL}")
            raise
        except (KeyError, IndexError, ValueError) as e:
            print(
                f"{Fore.RED}Error parsing Etherscan API response: {e}{Style.RESET_ALL}"
            )
            raise

    def check_contract_creation_blocks(self) -> Dict[str, int]:
        """Check and log creation blocks for all contracts."""
        contracts = list(self.contracts.keys())
        creation_blocks = {}

        print(
            f"\n{Fore.CYAN}Checking creation blocks for {len(contracts)} contracts{Style.RESET_ALL}"
        )
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")

        for contract_name in contracts:
            try:
                contract_config = self.contracts[contract_name]
                contract_address = contract_config["address"]

                print(
                    f"\n{Fore.GREEN}Checking contract: {contract_name}{Style.RESET_ALL}"
                )
                print(f"{Fore.YELLOW}Address: {contract_address}{Style.RESET_ALL}")

                creation_block = self.get_contract_creation_block(contract_address)
                creation_blocks[contract_name] = creation_block

                # Get block timestamp
                w3 = self.get_next_w3()
                block = w3.eth.get_block(creation_block)
                timestamp = datetime.fromtimestamp(block.timestamp)

                print(
                    f"{Fore.GREEN}Creation block: {creation_block} ({timestamp}){Style.RESET_ALL}"
                )

            except Exception as e:
                print(
                    f"{Fore.RED}Error checking creation block for {contract_name}: {e}{Style.RESET_ALL}"
                )
                continue

        print(f"\n{Fore.CYAN}Creation block summary:{Style.RESET_ALL}")
        for contract_name, block in creation_blocks.items():
            print(f"{Fore.YELLOW}{contract_name}: Block {block}{Style.RESET_ALL}")

        return creation_blocks

    def collect_contract_data(
        self, contract_name: str, contract: Contract, creation_block: int
    ) -> pd.DataFrame:
        """Collect data for a specific contract."""
        contract_config = self.contracts[contract_name]
        contract_address = contract_config["address"]

        print(
            f"\n{Fore.GREEN}Collecting data for contract: {contract_name}{Style.RESET_ALL}"
        )
        print(f"{Fore.YELLOW}Address: {contract_address}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Start block: {creation_block}{Style.RESET_ALL}")

        # Get current block from any Web3 instance
        current_block = self.w3_instances[0].eth.block_number
        print(f"{Fore.YELLOW}Current block: {current_block}{Style.RESET_ALL}")
        print(
            f"{Fore.YELLOW}Functions to track: {[f['name'] for f in contract_config['functions_to_track']]}{Style.RESET_ALL}"
        )

        # Calculate actual blocks we'll process
        total_blocks = current_block - creation_block
        blocks_to_process = (total_blocks // self.blocks_period) * self.blocks_period
        data_points = (blocks_to_process // self.blocks_period) + 1

        print(f"{Fore.YELLOW}Total blocks in range: {total_blocks}{Style.RESET_ALL}")
        print(
            f"{Fore.YELLOW}Blocks to process: {blocks_to_process} (every {self.blocks_period} blocks){Style.RESET_ALL}"
        )
        print(f"{Fore.YELLOW}Data points to collect: {data_points}{Style.RESET_ALL}\n")

        data_points_list = []
        last_call_time = 0

        # Create progress bar for blocks
        block_range = range(creation_block, current_block + 1, self.blocks_period)
        with tqdm(
            total=len(block_range),
            desc=f"{Fore.BLUE}Processing blocks{Style.RESET_ALL}",
            unit="block",
            leave=True,
        ) as pbar:
            for block_number in block_range:
                # Ensure we don't exceed the block retrieval period
                current_time = time.time()
                if current_time - last_call_time < self.block_retrieval_period:
                    time.sleep(
                        self.block_retrieval_period - (current_time - last_call_time)
                    )
                last_call_time = time.time()

                # Get block timestamp using round-robin RPC
                w3 = self.get_next_w3()
                block = w3.eth.get_block(block_number)
                timestamp = datetime.fromtimestamp(block.timestamp)

                # Update progress bar description with current block info
                pbar.set_description(
                    f"{Fore.BLUE}Processing block {block_number} ({timestamp}){Style.RESET_ALL}"
                )

                # Collect data for each function to track
                row_data = {"block_number": block_number, "timestamp": timestamp}

                for func_config in contract_config["functions_to_track"]:
                    try:
                        func = getattr(contract.functions, func_config["name"])
                        result = func(*func_config["params"]).call(
                            block_identifier=block_number
                        )

                        # Handle tuple results
                        if isinstance(result, tuple):
                            for i, col_name in enumerate(func_config["column_names"]):
                                # Convert tuple element to string and remove any brackets
                                value = str(result[i]).strip("[]")
                                row_data[col_name] = value
                        else:
                            # Convert single result to string and remove any brackets
                            value = str(result).strip("[]")
                            row_data[func_config["column_names"][0]] = value
                    except Exception as e:
                        print(
                            f"\n{Fore.RED}Error collecting {func_config['name']} at block {block_number}: {e}{Style.RESET_ALL}"
                        )
                        continue

                data_points_list.append(row_data)
                pbar.update(1)

        print(
            f"\n{Fore.GREEN}Completed collecting data for {contract_name}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.GREEN}Total data points collected: {len(data_points_list)}{Style.RESET_ALL}"
        )
        return pd.DataFrame(data_points_list)

    def process_contract(
        self, contract_name: str, creation_block: int
    ) -> Optional[pd.DataFrame]:
        """Process a single contract and return its DataFrame."""
        try:
            contract_config = self.contracts[contract_name]
            w3 = self.get_next_w3()

            contract = w3.eth.contract(
                address=Web3.to_checksum_address(contract_config["address"]),
                abi=contract_config["abi"],
            )

            df = self.collect_contract_data(contract_name, contract, creation_block)
            return df
        except Exception as e:
            print(
                f"{Fore.RED}Error processing contract {contract_name}: {e}{Style.RESET_ALL}"
            )
            return None

    def collect_all_data(self):
        """Collect data for all configured contracts in parallel."""
        # First, check all contract creation blocks
        creation_blocks = self.check_contract_creation_blocks()

        if not creation_blocks:
            print(f"{Fore.RED}No valid contracts found. Exiting.{Style.RESET_ALL}")
            return

        contracts = list(creation_blocks.keys())
        max_workers = min(len(self.w3_instances), len(contracts))

        print(
            f"\n{Fore.CYAN}Starting data collection for {len(contracts)} contracts{Style.RESET_ALL}"
        )
        print(f"{Fore.CYAN}Using {max_workers} parallel workers{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_contract = {
                executor.submit(
                    self.process_contract, contract_name, creation_blocks[contract_name]
                ): contract_name
                for contract_name in contracts
            }

            # Process completed tasks with progress bar
            with tqdm(
                total=len(contracts),
                desc=f"{Fore.CYAN}Overall progress{Style.RESET_ALL}",
                unit="contract",
                leave=True,
            ) as pbar:
                for future in as_completed(future_to_contract):
                    contract_name = future_to_contract[future]
                    try:
                        df = future.result()
                        if df is not None:
                            # Save to CSV
                            output_file = os.path.join(
                                self.data_dir, f"{contract_name}.csv"
                            )
                            df.to_csv(output_file, index=False)
                            print(
                                f"\n{Fore.GREEN}Saved data to {output_file}{Style.RESET_ALL}"
                            )
                    except Exception as e:
                        print(
                            f"\n{Fore.RED}Error processing {contract_name}: {e}{Style.RESET_ALL}"
                        )
                    finally:
                        pbar.update(1)

        print(f"\n{Fore.GREEN}Data collection completed!{Style.RESET_ALL}")


def main():
    parser = argparse.ArgumentParser(description="Collect blockchain data")
    parser.add_argument(
        "--asset",
        choices=["ETH", "USD"],
        default="ETH",
        help="Asset to collect data for (default: ETH)",
    )
    args = parser.parse_args()

    collector = BlockchainDataCollector(asset=args.asset)
    collector.collect_all_data()


if __name__ == "__main__":
    main()
