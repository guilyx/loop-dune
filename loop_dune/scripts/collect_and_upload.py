#!/usr/bin/env python
"""
Script to collect data for all assets and upload to Dune Analytics.
"""

import os
import subprocess
import sys
import time
import argparse
from typing import List, Dict, Tuple
from datetime import datetime
from web3 import Web3
import json

from colorama import Fore, Style, init

# Initialize colorama for cross-platform color support
init()

# Asset configurations
ASSETS = ["ETH", "USD", "BNB"]

# Block periods for each asset
BLOCK_PERIODS = {
    "ETH": 3500,
    "USD": 3500,
    "BNB": 12000,
}

# ERC20 ABI for balanceOf function
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    }
]


def collect_token_balance(
    web3: Web3,
    token_address: str,
    contract_address: str,
    start_block: int,
    end_block: int,
    block_period: int,
) -> List[Dict]:
    """
    Collect token balances for a contract over a range of blocks.

    Args:
        web3: Web3 instance
        token_address: Address of the token contract
        contract_address: Address of the contract to check balance for
        start_block: Starting block number
        end_block: Ending block number
        block_period: Number of blocks between samples

    Returns:
        List of dictionaries containing block numbers and balances
    """
    token_contract = web3.eth.contract(address=token_address, abi=ERC20_ABI)
    balances = []

    for block in range(start_block, end_block + 1, block_period):
        try:
            balance = token_contract.functions.balanceOf(contract_address).call(
                block_identifier=block
            )
            balances.append(
                {
                    "block": block,
                    "balance": balance,
                    "timestamp": web3.eth.get_block(block)["timestamp"],
                }
            )
        except Exception as e:
            print(f"Error getting balance at block {block}: {e}")
            continue

    return balances


def collect_balances_for_asset(
    asset: str, web3: Web3, creation_blocks: Dict[str, int]
) -> bool:
    """
    Collect token balances for a specific asset.

    Args:
        asset: Asset to collect balances for
        web3: Web3 instance to use
        creation_blocks: Dictionary of contract names to creation blocks

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Collecting balances for {asset}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")

    # Load contract configurations
    with open("loop_dune/config/contracts.py", "r") as f:
        contracts_config = eval(f.read())

    balances_config = contracts_config["CONTRACTS"][asset]["balances"]

    for balance_config in balances_config:
        try:
            contract_name = balance_config["name"].lower().replace(" ", "_")

            # Get creation block or use last block period if not found
            start_block = creation_blocks.get(
                contract_name, web3.eth.block_number - BLOCK_PERIODS[asset]
            )

            # Get current block
            current_block = web3.eth.block_number

            # Collect balances
            balances = collect_token_balance(
                web3,
                balance_config["token_address"],
                balance_config["contract_address"],
                start_block,
                current_block,
                BLOCK_PERIODS[asset],
            )

            # Save to CSV
            output_file = f"data/{asset.lower()}_{contract_name}.csv"
            os.makedirs("data", exist_ok=True)

            with open(output_file, "w") as f:
                f.write("block,timestamp,balance\n")
                for balance in balances:
                    f.write(
                        f"{balance['block']},{balance['timestamp']},{balance['balance']}\n"
                    )

            print(
                f"{Fore.GREEN}Successfully collected balances for {balance_config['name']}{Style.RESET_ALL}"
            )

        except Exception as e:
            print(
                f"{Fore.RED}Error collecting balances for {balance_config['name']}: {e}{Style.RESET_ALL}"
            )
            continue

    return True


# Contract configurations for each asset
CONTRACTS = {
    "ETH": [
        {
            "file": "lp_eth_pool.csv",
            "name": "Loop ETH Lending Market",
            "description": "Loop ETH Lending Market data",
        },
        {
            "file": "slp_eth.csv",
            "name": "slpETH supply data",
            "description": "slpETH supply data",
        },
        {
            "file": "eth_yneth_cdp_vault.csv",
            "name": "Loop ynETH CDP Vault",
            "description": "Loop ynETH CDP Vault data",
        },
        {
            "file": "eth_ynethx_cdp_vault.csv",
            "name": "Loop ynETHx CDP Vault",
            "description": "Loop ynETHx CDP Vault data",
        },
        {
            "file": "loop_yneth_cdp_balance.csv",
            "name": "Loop ynETH CDP Balance",
            "description": "ynETH balance in CDP Vault",
        },
        {
            "file": "loop_ynethx_cdp_balance.csv",
            "name": "Loop ynETHx CDP Balance",
            "description": "ynETHx balance in CDP Vault",
        },
        {
            "file": "loop_lpeth_slp_balance.csv",
            "name": "Loop lpETH SLP Balance",
            "description": "lpETH balance in SLP contract",
        }
    ],
    "USD": [
        {
            "file": "lp_usd_pool.csv",
            "name": "Loop USD Lending Market",
            "description": "Loop USD Lending Market data",
        },
        {
            "file": "slp_usd.csv",
            "name": "slpUSD supply data",
            "description": "slpUSD supply data",
        },
        {
            "file": "usd_cdp_vault.csv",
            "name": "Loop USD CDP Vault",
            "description": "Loop USD CDP Vault data",
        },
        {
            "file": "loop_deusd_cdp_balance.csv",
            "name": "Loop DEUSD CDP Balance",
            "description": "DEUSD balance in CDP Vault",
        },
        {
            "file": "loop_lpusd_slp_balance.csv",
            "name": "Loop lpUSD SLP Balance",
            "description": "lpUSD balance in SLP contract",
        },
    ],
    "BNB": [
        {
            "file": "lp_bnb_pool.csv",
            "name": "Loop BNB Lending Market",
            "description": "Loop BNB Lending Market data",
        },
        {
            "file": "slp_bnb.csv",
            "name": "slpBNB supply data",
            "description": "slpBNB supply data",
        },
        {
            "file": "bnb_cdp_vault.csv",
            "name": "Loop BNB CDP Vault",
            "description": "Loop BNB CDP Vault data",
        },
        {
            "file": "loop_clisbnb_cdp_balance.csv",
            "name": "Loop clisBNB CDP Balance",
            "description": "clisBNB balance in CDP Vault",
        },
        {
            "file": "loop_lpbnb_slp_balance.csv",
            "name": "Loop lpBNB SLP Balance",
            "description": "lpBNB balance in SLP contract",
        },
    ],
}


def run_command(command: List[str], description: str) -> Tuple[bool, str]:
    """
    Run a command and return its success status and output.

    Args:
        command: Command to run
        description: Description of the command

    Returns:
        Tuple of (success, output)
    """
    print(f"\n{Fore.CYAN}Running: {description}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Command: {' '.join(command)}{Style.RESET_ALL}")

    try:
        # Run the command and capture output in real-time
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

        # Print output in real-time
        while True:
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                print(output.strip())

        # Get the return code
        return_code = process.poll()
        success = return_code == 0

        if success:
            print(f"{Fore.GREEN}Command completed successfully{Style.RESET_ALL}")
        else:
            print(
                f"{Fore.RED}Command failed with return code {return_code}{Style.RESET_ALL}"
            )

        return success, ""

    except Exception as e:
        print(f"{Fore.RED}Error running command: {e}{Style.RESET_ALL}")
        return False, str(e)


def collect_data_for_asset(asset: str) -> bool:
    """
    Collect data for a specific asset.

    Args:
        asset: Asset to collect data for

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Collecting data for {asset}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")

    command = [
        "poetry",
        "run",
        "loop-collect",
        "--asset",
        asset,
        "--blocks-period",
        str(BLOCK_PERIODS[asset]),
    ]
    success, _ = run_command(command, f"Collect data for {asset}")

    return success


def upload_data_for_asset(asset: str) -> bool:
    """
    Upload data for a specific asset.

    Args:
        asset: Asset to upload data for

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Uploading data for {asset}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")

    success = True

    for contract in CONTRACTS[asset]:
        file_path = os.path.join("data", contract["file"])

        # Check if file exists
        if not os.path.exists(file_path):
            print(
                f"{Fore.YELLOW}Warning: File {file_path} does not exist. Skipping.{Style.RESET_ALL}"
            )
            continue

        command = [
            "poetry",
            "run",
            "loop-upload",
            "-f",
            file_path,
            "-n",
            contract["name"],
            "-d",
            contract["description"],
        ]

        cmd_success, _ = run_command(command, f"Upload {contract['file']} for {asset}")
        success = success and cmd_success

    return success


def run_collection_and_upload():
    """Run the collection and upload process for all assets."""
    print(
        f"{Fore.CYAN}Starting data collection and upload for all assets{Style.RESET_ALL}"
    )
    print(
        f"{Fore.CYAN}Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}"
    )

    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)

    # Collect and upload data for each asset
    for asset in ASSETS:
        # Collect data
        collect_success = collect_data_for_asset(asset)

        if collect_success:
            # Upload data
            upload_success = upload_data_for_asset(asset)

            if upload_success:
                print(
                    f"{Fore.GREEN}Successfully collected and uploaded data for {asset}{Style.RESET_ALL}"
                )
            else:
                print(
                    f"{Fore.RED}Failed to upload data for {asset}{Style.RESET_ALL}"
                )
        else:
            print(
                f"{Fore.RED}Failed to collect data for {asset}. Skipping upload.{Style.RESET_ALL}"
            )

        # Add a delay between assets
        if asset != ASSETS[-1]:
            print(
                f"{Fore.YELLOW}Waiting 5 seconds before processing next asset...{Style.RESET_ALL}"
            )
            time.sleep(5)

    print(
        f"\n{Fore.GREEN}Data collection and upload completed for all assets{Style.RESET_ALL}"
    )
    print(
        f"{Fore.GREEN}Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}"
    )


def main():
    """Main function to parse arguments and run the collection and upload process."""
    parser = argparse.ArgumentParser(
        description="Collect and upload data for all assets"
    )
    parser.add_argument(
        "--cron",
        type=str,
        help="Cron expression for scheduling (e.g., '0 */6 * * *' for every 6 hours)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        help="Interval in minutes between runs (alternative to cron)",
    )
    args = parser.parse_args()

    if args.cron:
        # Parse cron expression
        try:
            from croniter import croniter
            from datetime import datetime

            # Validate cron expression
            croniter(args.cron, datetime.now())

            print(
                f"{Fore.CYAN}Running with cron schedule: {args.cron}{Style.RESET_ALL}"
            )

            while True:
                # Run the collection and upload process
                run_collection_and_upload()

                # Calculate next run time
                cron = croniter(args.cron, datetime.now())
                next_run = cron.get_next(datetime)
                wait_seconds = (next_run - datetime.now()).total_seconds()

                print(
                    f"{Fore.CYAN}Next run scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}"
                )
                print(
                    f"{Fore.CYAN}Waiting {wait_seconds:.0f} seconds...{Style.RESET_ALL}"
                )

                # Sleep until next run
                time.sleep(wait_seconds)

        except ImportError:
            print(
                f"{Fore.RED}Error: croniter package not installed. Please install it with 'pip install croniter'{Style.RESET_ALL}"
            )
            sys.exit(1)
        except ValueError as e:
            print(f"{Fore.RED}Error: Invalid cron expression: {e}{Style.RESET_ALL}")
            sys.exit(1)
    elif args.interval:
        # Run with fixed interval
        print(
            f"{Fore.CYAN}Running with interval of {args.interval} minutes{Style.RESET_ALL}"
        )

        while True:
            # Run the collection and upload process
            run_collection_and_upload()

            # Calculate next run time
            next_run = datetime.now().timestamp() + (args.interval * 60)
            wait_seconds = args.interval * 60

            print(
                f"{Fore.CYAN}Next run scheduled for: {datetime.fromtimestamp(next_run).strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}"
            )
            print(f"{Fore.CYAN}Waiting {wait_seconds} seconds...{Style.RESET_ALL}")

            # Sleep until next run
            time.sleep(wait_seconds)
    else:
        # Run once
        run_collection_and_upload()


if __name__ == "__main__":
    main()
