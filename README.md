# Loop Dune - Blockchain Data Collection and Sync

This project collects historical data from various Spectra Protocol contracts on the Ethereum blockchain and syncs it to Dune Analytics. It includes tools for data collection, analysis, and automated syncing to Dune Analytics.

## Features

- Historical data collection from Ethereum contracts
- Automated syncing to Dune Analytics
- Interactive dashboard for data visualization
- Configurable data collection parameters
- Support for multiple RPC endpoints
- Scheduled data updates

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
- `DUNE_API_KEY`: Your Dune Analytics API key
- `ETH_RPC_URLS`: Comma-separated list of Ethereum RPC endpoints
- `BLOCK_PERIOD`: Number of blocks between data points
- `BLOCK_RETRIEVAL_PERIOD`: Maximum seconds between RPC calls
- `DATA_DIR`: Directory to store CSV files

## Usage

### Data Collection
Collect historical data from contracts:
```bash
poetry run loop-collect
```

### Data Upload
Upload collected data to Dune Analytics:
```bash
poetry run loop-upload
```

### Dashboard
Launch the interactive dashboard:
```bash
poetry run loop-dashboard
```

### Sync Service
Run the automated sync service:
```bash
poetry run loop-sync
```

## Deployment to Heroku

1. Install Heroku CLI:
```bash
curl https://cli-assets.heroku.com/install.sh | sh
```

2. Login to Heroku:
```bash
heroku login
```

3. Create a new Heroku app:
```bash
heroku create loop-dune-sync
```

4. Set up environment variables:
```bash
heroku config:set DUNE_API_KEY=your_dune_api_key
heroku config:set ETH_RPC_URLS=your_rpc_urls
heroku config:set BLOCK_PERIOD=1000
heroku config:set BLOCK_RETRIEVAL_PERIOD=0.1
```

5. Deploy the application:
```bash
git add .
git commit -m "Prepare for Heroku deployment"
git push heroku master
```

6. Start the worker dyno:
```bash
heroku ps:scale worker=1
```

7. Monitor logs:
```bash
heroku logs --tail
```

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

## Development

### Running Tests
```bash
poetry run pytest
```

### Code Formatting
```bash
poetry run black .
poetry run isort .
```

### Type Checking
```bash
poetry run mypy .
```

## License

MIT License