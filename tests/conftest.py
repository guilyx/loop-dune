import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime
import os
import sys
from web3 import Web3

# Ensure we're using the project's virtual environment
if hasattr(sys, "real_prefix") or (
    hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
):
    # We're in a virtual environment
    pass
else:
    # Not in a virtual environment, raise a warning
    pytest.warn(
        "Tests are not running in a virtual environment. This may cause conflicts with system packages."
    )


@pytest.fixture(autouse=True)
def mock_env():
    """Mock environment variables for all tests"""
    with patch.dict(
        os.environ,
        {
            "DUNE_API_KEY": "test_api_key",
            "ETH_RPC_URLS": "http://localhost:8545",
            "BLOCK_PERIOD": "100",
            "BLOCK_RETRIEVAL_PERIOD": "1000",
        },
    ):
        yield


@pytest.fixture
def mock_web3():
    """Mock Web3 instance"""
    with patch("web3.Web3") as mock:
        # Create a mock Web3 instance
        mock_instance = MagicMock()
        mock_instance.eth = MagicMock()
        mock_instance.eth.block_number = 1000
        mock_instance.eth.contract.return_value = MagicMock()
        mock_instance.is_connected.return_value = True

        # Mock HTTPProvider
        mock_provider = MagicMock()
        mock_instance.eth.contract.return_value = Mock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_requests():
    """Mock requests for API calls"""
    with patch("requests.post") as mock:
        mock.return_value.status_code = 200
        mock.return_value.json.return_value = {"success": True}
        yield mock


@pytest.fixture
def sample_data():
    """Sample DataFrame for testing"""
    return pd.DataFrame(
        {
            "block_number": [1000, 1001],
            "timestamp": [datetime.now(), datetime.now()],
            "value": [100, 101],
        }
    )


@pytest.fixture
def mock_contract():
    """Mock contract instance"""
    contract = Mock()
    contract.functions = Mock()
    contract.functions.get_value.return_value = Mock()
    contract.functions.get_value.return_value.call.return_value = 100
    return contract
