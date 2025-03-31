# Loop Dune - Blockchain Data Collection and Sync

[![Tests](https://github.com/wardn/loop-dune/actions/workflows/test.yml/badge.svg)](https://github.com/wardn/loop-dune/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/wardn/loop-dune/branch/master/graph/badge.svg)](https://codecov.io/gh/wardn/loop-dune)

This project collects historical data from various Spectra Protocol contracts on the Ethereum blockchain and syncs it to Dune Analytics. It includes tools for data collection, analysis, and automated syncing to Dune Analytics.

## Features

- Historical data collection from Ethereum contracts
- Interactive web dashboard for contract management and data collection
- Automated syncing to Dune Analytics
- Support for multiple RPC endpoints
- Configurable data collection parameters
- Scheduled data updates
- Contract management interface
- Docker support for sync service
- Automated testing and container builds

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

### Web Dashboard
Launch the interactive dashboard:
```bash
poetry run streamlit run loop_dune/dashboard.py
```

The dashboard provides three main sections:

1. **Contract Management**
   - View and select existing contracts
   - Add new contracts with custom configurations
   - Configure functions to track for each contract
   - Manage contract ABIs and parameters

2. **Data Collection**
   - Select contracts for data collection
   - Configure block ranges and collection parameters
   - Fetch and preview data
   - Save data to CSV files

3. **Dune Integration**
   - Upload collected data to Dune Analytics
   - Create new tables or insert into existing ones
   - Preview data before upload

### Command Line Tools

You can also use the command line tools directly:

```bash
# Collect historical data
poetry run loop-collect

# Upload data to Dune
poetry run loop-upload

# Run automated sync service
poetry run loop-sync
```

### Docker Deployment

The sync service can be deployed using Docker:

```bash
# Build and run using docker-compose
docker-compose up -d

# Or build and run using Docker directly
docker build -t loop-dune-sync .
docker run -d \
  --name loop-dune-sync \
  -e DUNE_API_KEY=your_key \
  -e ETH_RPC_URLS=your_urls \
  -v $(pwd)/data:/app/data \
  loop-dune-sync
```

## Testing

Run the test suite:
```bash
poetry run pytest
```

The test suite includes:
- Unit tests for sync functionality
- Mocked Web3 and API calls
- Data validation tests
- Error handling tests

## CI/CD

The project uses GitHub Actions for:
- Automated testing on push and pull requests
- Docker image building and pushing to GitHub Container Registry
- Version tagging and release management

### GitHub Container Registry

Docker images are automatically built and pushed to GitHub Container Registry:
- Latest image: `ghcr.io/your-username/loop-dune:latest`
- Versioned images: `ghcr.io/your-username/loop-dune:v1.0.0`
- Branch images: `ghcr.io/your-username/loop-dune:main`

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

## License

MIT License