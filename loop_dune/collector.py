import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import argparse
import random
import sys

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
        Initialize the blockchain data collector.

        Args:
            asset: Asset type to collect data for (ETH, USD, or BNB)
        """
        if asset not in ["ETH", "USD", "BNB", "BTC"]:
            raise ValueError("Asset must be either 'ETH', 'USD', or 'BNB")

        self.asset = asset
        self.contracts = CONTRACTS[asset]
        self.chain_id = int(
            self.contracts.get("chain_id", 1)
        )  # Default to Ethereum mainnet (1)

        # Initialize Web3 with multiple RPC URLs
        if asset in ["BNB", "BTC"]:
            rpc_urls = os.getenv(f"BNB_RPC_URLS", "").split(",")
            if not rpc_urls or not rpc_urls[0]:
                raise ValueError(f"{asset}_RPC_URLS environment variable not set")
        else:
            rpc_urls = os.getenv(f"ETH_RPC_URLS", "").split(",")
            if not rpc_urls or not rpc_urls[0]:
                raise ValueError(f"ETH_RPC_URLS environment variable not set")

        self.rpc_urls = [url.strip() for url in rpc_urls if url.strip()]

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

        print(
            f"{Fore.GREEN}Initialized collector for {asset} (chain ID: {self.chain_id}){Style.RESET_ALL}"
        )

        self.blocks_period = int(os.getenv("BLOCKS_PERIOD", "100"))
        self.block_retrieval_period = float(os.getenv("BLOCK_RETRIEVAL_PERIOD", "60"))
        self.data_dir = os.getenv("DATA_DIR", "data")
        os.makedirs(self.data_dir, exist_ok=True)

        print(f"{Fore.CYAN}Blocks period: {self.blocks_period}{Style.RESET_ALL}")
        print(
            f"{Fore.CYAN}Block retrieval period: {self.block_retrieval_period}s{Style.RESET_ALL}"
        )
        print(f"{Fore.CYAN}Data directory: {self.data_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Asset: {asset}{Style.RESET_ALL}\n")

    def get_contract_creation_block(self, contract_address: str) -> int:
        """Get the block number where the contract was created using Etherscan API."""
        # Get API key from environment
        api_key = os.getenv("ETHERSCAN_API_KEY")
        if not api_key:
            raise ValueError("ETHERSCAN_API_KEY environment variable not set")

        # Prepare API request parameters
        params = {
            "chainid": self.chain_id,
            "module": "contract",
            "action": "getcontractcreation",
            "contractaddresses": contract_address,
            "apikey": api_key,
        }

        # Make API request to the unified Etherscan API
        url = f"https://api.etherscan.io/v2/api?{urlencode(params)}"

        print(
            f"{Fore.YELLOW}Fetching contract creation block from chain ID {self.chain_id}...{Style.RESET_ALL}"
        )

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            if data["status"] != "1":
                raise ValueError(f"Explorer API error: {data['message']}")

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
            print(f"{Fore.RED}Error fetching from explorer API: {e}{Style.RESET_ALL}")
            raise
        except (KeyError, IndexError, ValueError) as e:
            print(
                f"{Fore.RED}Error parsing explorer API response: {e}{Style.RESET_ALL}"
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

        # Handle regular contracts
        for contract_name in self.contracts:
            if contract_name in ["chain_id", "balances"]:
                continue
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
                block = self.w3.eth.get_block(creation_block)
                timestamp = datetime.fromtimestamp(block.timestamp)

                print(
                    f"{Fore.GREEN}Creation block: {creation_block} ({timestamp}){Style.RESET_ALL}"
                )

            except Exception as e:
                print(
                    f"{Fore.RED}Error checking creation block for {contract_name}: {e}{Style.RESET_ALL}"
                )
                continue

        # Handle balances contracts
        if "balances" in self.contracts:
            for balance_config in self.contracts["balances"]:
                contract_name = balance_config["name"].lower().replace(" ", "_")
                try:
                    creation_block = self.get_contract_creation_block(
                        balance_config["contract_address"]
                    )
                    creation_blocks[contract_name] = creation_block
                except Exception as e:
                    print(
                        f"{Fore.RED}Error getting creation block for {contract_name}: {e}{Style.RESET_ALL}"
                    )
                    continue

        print(f"\n{Fore.CYAN}Creation block summary:{Style.RESET_ALL}")
        for contract_name, block in creation_blocks.items():
            print(f"{Fore.YELLOW}{contract_name}: Block {block}{Style.RESET_ALL}")

        return creation_blocks

    def get_contract(self, contract_name: str) -> Contract:
        """
        Get a Web3 contract instance for the specified contract.

        Args:
            contract_name: Name of the contract in CONTRACTS dict

        Returns:
            Web3 contract instance
        """
        contract_config = self.contracts[contract_name]
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(contract_config["address"]),
            abi=contract_config["abi"],
        )

    def collect_contract_data(
        self,
        contract_name: str,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        blocks_period: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Collect data for a specific contract.

        Args:
            contract_name: Name of the contract to collect data for
            start_block: Block number to start collecting from (optional)
            end_block: Block number to end collecting at (optional)
            blocks_period: Number of blocks to collect data for each period (optional)

        Returns:
            DataFrame with collected data
        """
        print(f"\n{Fore.CYAN}Collecting data for {contract_name}...{Style.RESET_ALL}")

        # Get contract configuration
        contract_config = self.contracts[contract_name]
        contract = self.get_contract(contract_name)

        # Get contract creation block if start_block not provided
        if start_block is None:
            try:
                start_block = self.get_contract_creation_block(
                    contract_config["address"]
                )
            except Exception as e:
                print(f"Error getting contract creation block: {e}")
                return pd.DataFrame()

        # Set end_block to current block if not provided
        if end_block is None:
            end_block = self.w3.eth.block_number

        # Use provided blocks_period or default
        blocks_period = blocks_period or self.blocks_period

        print(f"{Fore.YELLOW}Start block: {start_block}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}End block: {end_block}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Using block period of {blocks_period}{Style.RESET_ALL}")

        # Calculate total blocks and data points
        total_blocks = end_block - start_block
        blocks_to_process = (total_blocks // blocks_period) * blocks_period
        data_points = (blocks_to_process // blocks_period) + 1

        print(f"{Fore.YELLOW}Total blocks in range: {total_blocks}{Style.RESET_ALL}")
        print(
            f"{Fore.YELLOW}Blocks to process: {blocks_to_process} (every {blocks_period} blocks){Style.RESET_ALL}"
        )
        print(f"{Fore.YELLOW}Data points to collect: {data_points}{Style.RESET_ALL}")

        # Collect data for each block
        data = []
        last_call_time = 0

        # Create progress bar for blocks
        block_range = range(start_block, end_block + 1, blocks_period)
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

                # Get block timestamp
                block = self.w3.eth.get_block(block_number)
                timestamp = datetime.fromtimestamp(block.timestamp)

                # Update progress bar description with current block info
                pbar.set_description(
                    f"{Fore.BLUE}Processing block {block_number} ({timestamp}){Style.RESET_ALL}"
                )

                # Collect data for all functions at this block
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
                            f"{Fore.RED}Error collecting {func_config['name']} at block {block_number}: {e}{Style.RESET_ALL}"
                        )
                        # Continue with other functions even if one fails

                data.append(row_data)
                pbar.update(1)

        # Create DataFrame
        df = pd.DataFrame(data)

        # Save to CSV
        csv_path = os.path.join(self.data_dir, f"{contract_name}.csv")
        if os.path.exists(csv_path):
            # Append to existing CSV
            existing_df = pd.read_csv(csv_path)
            df = (
                pd.concat([existing_df, df])
                .drop_duplicates(subset=["block_number"])
                .sort_values("block_number")
            )

        df.to_csv(csv_path, index=False)
        print(f"{Fore.GREEN}Saved {len(df)} data points to {csv_path}{Style.RESET_ALL}")

        return df

    def process_contract(
        self, contract_name: str, creation_block: int
    ) -> Optional[pd.DataFrame]:
        """Process a single contract and return its DataFrame."""
        try:
            contract_config = self.contracts[contract_name]

            contract = self.get_contract(contract_name)

            df = self.collect_contract_data(contract_name, creation_block)
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
        max_workers = min(len(self.rpc_urls), len(contracts))

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

    def collect_historical_data(
        self, end_block: Optional[int] = None, blocks_period: Optional[int] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Collect historical data for all contracts.

        Args:
            end_block: Optional end block number. If not provided, uses the current block.
            blocks_period: Optional number of blocks to collect data for each period.

        Returns:
            Dictionary of contract names to DataFrames
        """
        print(
            f"\n{Fore.CYAN}Collecting historical data for {self.asset}...{Style.RESET_ALL}"
        )

        # Get current block from any Web3 instance if end_block not specified
        if end_block is None:
            end_block = self.w3.eth.block_number
        print(f"{Fore.YELLOW}End block: {end_block}{Style.RESET_ALL}")
        print(
            f"{Fore.YELLOW}Blocks period: {blocks_period or self.blocks_period}{Style.RESET_ALL}"
        )

        # Get contract creation blocks
        creation_blocks = {}
        # Handle regular contracts
        for contract_name in self.contracts:
            if contract_name in ["chain_id", "balances"]:
                continue
            try:
                creation_block = self.get_contract_creation_block(
                    self.contracts[contract_name]["address"]
                )
                creation_blocks[contract_name] = creation_block
            except Exception as e:
                print(
                    f"{Fore.RED}Error getting creation block for {contract_name}: {e}{Style.RESET_ALL}"
                )
                continue

        # Handle balances contracts
        if "balances" in self.contracts:
            for balance_config in self.contracts["balances"]:
                contract_name = balance_config["name"].lower().replace(" ", "_")
                try:
                    creation_block = self.get_contract_creation_block(
                        balance_config["contract_address"]
                    )
                    creation_blocks[contract_name] = creation_block
                except Exception as e:
                    print(
                        f"{Fore.RED}Error getting creation block for {contract_name}: {e}{Style.RESET_ALL}"
                    )
                    continue

        # Collect data for each contract
        results = {}

        # First handle regular contracts
        contracts = [
            c for c in self.contracts.keys() if c not in ["chain_id", "balances"]
        ]
        max_workers = min(len(self.rpc_urls), len(contracts))

        print(
            f"{Fore.CYAN}Collecting data for {len(contracts)} regular contracts with {max_workers} workers{Style.RESET_ALL}"
        )

        if len(contracts) > 0:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for contract_name in contracts:
                    creation_block = creation_blocks.get(contract_name)
                    if not creation_block:
                        continue

                    # Check if CSV file exists and get the latest block number
                    csv_path = os.path.join(self.data_dir, f"{contract_name}.csv")
                    start_block = creation_block

                    if os.path.exists(csv_path):
                        try:
                            existing_df = pd.read_csv(csv_path)
                            if (
                                not existing_df.empty
                                and "block_number" in existing_df.columns
                            ):
                                latest_block = existing_df["block_number"].max()
                                if latest_block < end_block - 3500:
                                    start_block = latest_block + 1
                                    print(
                                        f"{Fore.GREEN}Resuming collection for {contract_name} from block {start_block}{Style.RESET_ALL}"
                                    )
                                else:
                                    print(
                                        f"{Fore.YELLOW}Data for {contract_name} is already up to date{Style.RESET_ALL}"
                                    )
                                    results[contract_name] = existing_df
                                    continue
                        except Exception as e:
                            print(
                                f"{Fore.RED}Error reading existing CSV for {contract_name}: {e}{Style.RESET_ALL}"
                            )

                    if start_block >= end_block:
                        print(
                            f"{Fore.YELLOW}No new blocks to collect for {contract_name}{Style.RESET_ALL}"
                        )
                        if os.path.exists(csv_path):
                            results[contract_name] = pd.read_csv(csv_path)
                        continue

                    futures.append(
                        executor.submit(
                            self.collect_contract_data,
                            contract_name,
                            start_block,
                            end_block,
                            blocks_period,
                        )
                    )

                # Collect results for regular contracts
                for contract_name, future in zip(contracts, futures):
                    try:
                        df = future.result()
                        if df is not None and not df.empty:
                            results[contract_name] = df
                    except Exception as e:
                        print(
                            f"{Fore.RED}Error collecting data for {contract_name}: {e}{Style.RESET_ALL}"
                        )

        # Now handle balance contracts
        if "balances" in self.contracts:
            print(f"\n{Fore.CYAN}Collecting balance data...{Style.RESET_ALL}")

            # ERC20 ABI for balanceOf function
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function",
                }
            ]

            # Prepare balance collection tasks
            balance_tasks = []
            for balance_config in self.contracts["balances"]:
                contract_name = balance_config["name"].lower().replace(" ", "_")
                creation_block = creation_blocks.get(contract_name)
                if not creation_block:
                    continue

                # Check existing data
                csv_path = os.path.join(self.data_dir, f"{contract_name}.csv")
                start_block = creation_block

                if os.path.exists(csv_path):
                    try:
                        existing_df = pd.read_csv(csv_path)
                        if (
                            not existing_df.empty
                            and "block_number" in existing_df.columns
                        ):
                            latest_block = existing_df["block_number"].max()
                            if latest_block < end_block:
                                start_block = latest_block + 1
                                print(
                                    f"{Fore.GREEN}Resuming balance collection for {contract_name} from block {start_block}{Style.RESET_ALL}"
                                )
                            else:
                                print(
                                    f"{Fore.YELLOW}Balance data for {contract_name} is already up to date{Style.RESET_ALL}"
                                )
                                results[contract_name] = existing_df
                                continue
                    except Exception as e:
                        print(
                            f"{Fore.RED}Error reading existing CSV for {contract_name}: {e}{Style.RESET_ALL}"
                        )

                balance_tasks.append(
                    {
                        "contract_name": contract_name,
                        "token_address": balance_config["token_address"],
                        "contract_address": balance_config["contract_address"],
                        "start_block": start_block,
                        "end_block": end_block,
                        "blocks_period": blocks_period or self.blocks_period,
                        "csv_path": csv_path,
                    }
                )

            if balance_tasks:
                max_workers = min(len(self.rpc_urls), len(balance_tasks))
                print(
                    f"{Fore.CYAN}Collecting balance data for {len(balance_tasks)} contracts with {max_workers} workers{Style.RESET_ALL}"
                )

                def collect_balance_data(task):
                    try:
                        # Create Web3 instance with random RPC
                        w3 = Web3(Web3.HTTPProvider(random.choice(self.rpc_urls)))
                        if self.chain_id in [56, 97]:
                            from web3.middleware import geth_poa_middleware

                            w3.middleware_onion.inject(geth_poa_middleware, layer=0)

                        # Create token contract
                        token_contract = w3.eth.contract(
                            address=Web3.to_checksum_address(task["token_address"]),
                            abi=erc20_abi,
                        )

                        data = []
                        last_call_time = 0

                        # Create progress bar for blocks
                        block_range = range(
                            task["start_block"],
                            task["end_block"] + 1,
                            task["blocks_period"],
                        )
                        with tqdm(
                            total=len(block_range),
                            desc=f"{Fore.BLUE}Processing {task['contract_name']}{Style.RESET_ALL}",
                            unit="block",
                            leave=True,
                        ) as pbar:
                            for block in block_range:
                                # Rate limiting
                                current_time = time.time()
                                if (
                                    current_time - last_call_time
                                    < self.block_retrieval_period
                                ):
                                    time.sleep(
                                        self.block_retrieval_period
                                        - (current_time - last_call_time)
                                    )
                                last_call_time = time.time()

                                try:
                                    # Get block timestamp first
                                    block_data = w3.eth.get_block(block)
                                    timestamp = datetime.fromtimestamp(
                                        block_data["timestamp"]
                                    )

                                    # Update progress bar description
                                    pbar.set_description(
                                        f"{Fore.BLUE}{task['contract_name']} at block {block} ({timestamp}){Style.RESET_ALL}"
                                    )

                                    # Get balance
                                    balance = token_contract.functions.balanceOf(
                                        Web3.to_checksum_address(
                                            task["contract_address"]
                                        )
                                    ).call(block_identifier=block)

                                    data.append(
                                        {
                                            "block_number": block,
                                            "timestamp": timestamp,
                                            "balance": balance,
                                        }
                                    )

                                except Exception as e:
                                    print(
                                        f"{Fore.RED}Error at block {block} for {task['contract_name']}: {e}{Style.RESET_ALL}"
                                    )
                                    continue
                                finally:
                                    pbar.update(1)

                        if data:
                            df = pd.DataFrame(data)

                            # Handle existing data
                            if os.path.exists(task["csv_path"]):
                                existing_df = pd.read_csv(task["csv_path"])
                                df = (
                                    pd.concat([existing_df, df])
                                    .drop_duplicates(subset=["block_number"])
                                    .sort_values("block_number")
                                )

                            df.to_csv(task["csv_path"], index=False)
                            print(
                                f"{Fore.GREEN}Saved {len(df)} data points for {task['contract_name']} to {task['csv_path']}{Style.RESET_ALL}"
                            )
                            return task["contract_name"], df
                        return task["contract_name"], None

                    except Exception as e:
                        print(
                            f"{Fore.RED}Error collecting balance data for {task['contract_name']}: {e}{Style.RESET_ALL}"
                        )
                        return task["contract_name"], None

                # Create overall progress bar for balance tasks
                with tqdm(
                    total=len(balance_tasks),
                    desc=f"{Fore.CYAN}Overall balance collection progress{Style.RESET_ALL}",
                    unit="contract",
                    leave=True,
                ) as overall_pbar:
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = [
                            executor.submit(collect_balance_data, task)
                            for task in balance_tasks
                        ]

                        for future in as_completed(futures):
                            try:
                                contract_name, df = future.result()
                                if df is not None:
                                    results[contract_name] = df
                            except Exception as e:
                                print(
                                    f"{Fore.RED}Error processing balance task: {e}{Style.RESET_ALL}"
                                )
                            finally:
                                overall_pbar.update(1)

        return results


def main():
    """Main function to collect historical data for all contracts."""
    parser = argparse.ArgumentParser(
        description="Collect historical data for contracts"
    )
    parser.add_argument(
        "--asset",
        type=str,
        choices=["ETH", "USD", "BNB", "BTC"],
        required=True,
        help="Asset to collect data for (ETH, USD, BTC or BNB)",
    )
    parser.add_argument(
        "--end-block",
        type=int,
        help="Block number to end collecting at (optional)",
    )
    parser.add_argument(
        "--blocks-period",
        type=int,
        help="Number of blocks to collect data for each period (optional)",
    )
    args = parser.parse_args()

    try:
        collector = BlockchainDataCollector(args.asset)
        collector.collect_historical_data(
            end_block=args.end_block,
            blocks_period=args.blocks_period,
        )
    except Exception as e:
        print(f"Error collecting data: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
