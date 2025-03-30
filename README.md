# Loop Dune - Blockchain Data Collection

This project collects historical data from various Spectra Protocol contracts on the Ethereum blockchain and stores it in CSV format.

## Setup

1. Install Poetry:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Install dependencies:
```bash
poetry install
```

3. Configure environment variables:
```bash
cp .env.example .env
```
Edit `.env` with your configuration:
- `ETH_RPC_URL`: Your Ethereum RPC endpoint
- `BLOCKS_PERIOD`: Number of blocks between data points
- `BLOCK_RETRIEVAL_PERIOD`: Maximum seconds between RPC calls
- `DATA_DIR`: Directory to store CSV files

## Usage

Run the data collector:
```bash
poetry run python src/collector.py
```

This will:
1. Connect to the Ethereum network
2. For each configured contract:
   - Collect data from the contract's creation block to the current block
   - Store the data in CSV format in the `data` directory
   - Each CSV includes block number, timestamp, and the tracked function values

## Data Format

Each contract's data is stored in a separate CSV file named `{contract_name}.csv` in the `data` directory. The CSV includes:
- `block_number`: The Ethereum block number
- `timestamp`: The block's timestamp
- Additional columns based on the tracked functions for each contract

## Configuration

Contract configurations are defined in `config/contracts.py`. Each contract entry includes:
- Contract address
- ABI file
- Start block
- Functions to track with their parameters and column names