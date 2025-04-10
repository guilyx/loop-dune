[![Tests](https://github.com/guilyx/loop-dune/actions/workflows/test.yml/badge.svg)](https://github.com/guilyx/loop-dune/actions/workflows/test.yml)

# Loop Dune

A Python package for collecting and uploading blockchain data to Dune Analytics.

## Features

- Collects data from multiple blockchain networks (Ethereum, BSC)
- Supports multiple assets (ETH, USD, BNB)
- Configurable block periods for each asset:
  - ETH: 3500 blocks
  - USD: 3500 blocks
  - BNB: 14000 blocks
- Incremental data collection (resumes from last collected block)
- Parallel data collection for multiple contracts
- Token balance tracking for contracts
- Automatic data upload to Dune Analytics
- Cron-based scheduling support

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/loop-dune.git
cd loop-dune
```

2. Install dependencies using Poetry:
```bash
poetry install
```

## Configuration

1. Create a `.env` file in the project root with the following variables:

```env
# RPC URLs (comma-separated)
ETH_RPC_URLS=https://eth-mainnet.g.alchemy.com/v2/your-api-key,https://eth-mainnet.public.blastapi.io
BNB_RPC_URLS=https://bsc-dataseed.binance.org,https://bsc-dataseed1.defibit.io

# API Keys
ETHERSCAN_API_KEY=your-etherscan-api-key
DUNE_API_KEY=your-dune-api-key

# Collection Settings
BLOCKS_PERIOD=100  # Default block period (can be overridden per asset)
BLOCK_RETRIEVAL_PERIOD=60  # Seconds between block retrievals
DATA_DIR=data  # Directory to store CSV files
```

2. Configure contracts in `loop_dune/config/contracts.py`:
```python
CONTRACTS = {
    "ETH": {
        "chain_id": 1,
        # Regular contract tracking
        "contract_name": {
            "address": "0x...",
            "abi": [...],
            "functions_to_track": [...]
        },
        # Token balance tracking
        "balances": [
            {
                "contract_address": "0x...",  # Contract to check balance for
                "token_address": "0x...",     # Token contract address
                "name": "Contract Token Balance",
                "description": "Token balance in contract"
            }
        ]
    },
    "BNB": {
        "chain_id": 56,
        "contract_name": {
            "address": "0x...",
            "abi": [...],
            "functions_to_track": [...]
        }
    }
}
```

## Usage

### Data Collection

Collect data for a specific asset:
```bash
# Collect ETH data
poetry run loop-collect --asset ETH

# Collect USD data
poetry run loop-collect --asset USD

# Collect BNB data
poetry run loop-collect --asset BNB

# Collect with custom block period
poetry run loop-collect --asset ETH --blocks-period 5000

# Collect up to a specific block
poetry run loop-collect --asset ETH --end-block 18000000
```

### Data Upload

Upload collected data to Dune Analytics:
```bash
# Upload ETH lending pool data
poetry run loop-upload -f data/lp_eth_pool.csv -n "Loop ETH Lending Market" -d "Loop ETH Lending Market data"

# Upload ETH supply data
poetry run loop-upload -f data/slp_eth.csv -n "slpETH supply data" -d "slpETH supply data"

# Upload token balance data
poetry run loop-upload -f data/eth_contract_token_balance.csv -n "Contract Token Balance" -d "Token balance in contract"
```

### Automated Collection and Upload

Run the automated collection and upload script:
```bash
# Run a single iteration (collects and uploads data once)
poetry run python loop_dune/scripts/collect_and_upload.py

# Run with cron schedule (every 6 hours)
poetry run python loop_dune/scripts/collect_and_upload.py --cron "0 */6 * * *"

# Run with fixed interval (every 30 minutes)
poetry run python loop_dune/scripts/collect_and_upload.py --interval 30
```

Example output:
```
==================================================
Collecting data for ETH
==================================================
Running command: poetry run loop-collect --asset ETH --blocks-period 3500

==================================================
Collecting balances for ETH
==================================================
Processing Contract Token Balance: 150/500 blocks [=====>   ] 30%
Successfully collected balances for Contract Token Balance

==================================================
Uploading data for ETH
==================================================
Running: Upload lp_eth_pool.csv for ETH
Command: poetry run loop-upload -f data/lp_eth_pool.csv -n "Loop ETH Lending Market" -d "Loop ETH Lending Market data"
Command completed successfully

Running: Upload eth_contract_token_balance.csv for ETH
Command: poetry run loop-upload -f data/eth_contract_token_balance.csv -n "Contract Token Balance" -d "Token balance in contract"
Command completed successfully

Successfully collected and uploaded data for ETH
Waiting 5 seconds before processing next asset...

==================================================
Collecting data for USD
==================================================
Running command: poetry run loop-collect --asset USD --blocks-period 3500

Script completed at 2024-02-20 15:30:00
```

The script shows:
- Section headers for each asset
- Command execution status
- Balance collection progress
- Upload status for each file
- Success/failure messages
- Timestamps for completion

## Development

### Running Tests

```bash
poetry run pytest
```

### Code Style

The project uses:
- Black for code formatting
- isort for import sorting
- flake8 for linting
- mypy for type checking

Run all checks:
```bash
poetry run black .
poetry run isort .
poetry run flake8 .
poetry run mypy .
```

## License

MIT
