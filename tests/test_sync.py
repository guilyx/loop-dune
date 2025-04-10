import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime

from loop_dune.sync import DuneSync
from loop_dune.collector import BlockchainDataCollector


@pytest.fixture
def mock_web3():
    with patch("web3.Web3") as mock:
        # Mock the provider's request function
        def mock_request_func(*args, **kwargs):
            if args[0]["method"] == "eth_blockNumber":
                return {"result": "0x3e8"}  # hex for 1000
            return {"result": None}

        # Mock the provider
        mock_provider = MagicMock()
        mock_provider.make_request.side_effect = mock_request_func
        mock_provider.request_func.return_value = mock_request_func

        # Mock eth module
        mock_eth = MagicMock()
        mock_eth.get_block_number.return_value = 1000
        mock_eth.block_number = 1000
        mock_eth.contract.return_value = Mock()

        # Mock Web3 instance
        mock_instance = MagicMock()
        mock_instance.eth = mock_eth
        mock_instance.provider = mock_provider
        mock_instance.is_connected.return_value = True
        mock_instance.manager.request_blocking.side_effect = mock_request_func

        # Mock the provider class
        mock_provider_class = MagicMock()
        mock_provider_class.return_value = mock_provider
        mock.HTTPProvider = mock_provider_class

        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_requests():
    with patch("requests.post") as mock:
        mock.return_value.status_code = 200
        mock.return_value.json.return_value = {"success": True}
        yield mock


@pytest.fixture
def sample_data():
    return pd.DataFrame(
        {
            "block_number": [1000, 1001],
            "timestamp": [datetime.now(), datetime.now()],
            "value": [100, 101],
        }
    )


@pytest.mark.web3
def test_dune_sync_initialization():
    """Test DuneSync initialization"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            sync = DuneSync(asset="ETH")
            assert sync.asset == "ETH"
            assert sync.namespace == "rangonomics"
            assert sync.api_key == "test_api_key"
            assert sync.w3 is not None


@pytest.mark.integration
def test_create_table():
    """Test table creation in Dune"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            with patch("requests.post") as mock_requests:
                mock_requests.return_value.status_code = 200
                mock_requests.return_value.json.return_value = {"success": True}

                sync = DuneSync(asset="ETH")
                df = pd.DataFrame(
                    {
                        "block_number": [1000],
                        "timestamp": [datetime.now()],
                        "value": [100],
                    }
                )

                result = sync.create_table("test_contract", df)
                assert result is True
                mock_requests.assert_called_once()


@pytest.mark.integration
def test_insert_data():
    """Test data insertion into Dune"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            with patch("requests.post") as mock_requests:
                mock_requests.return_value.status_code = 200
                mock_requests.return_value.json.return_value = {"rows_written": 1}

                sync = DuneSync(asset="ETH")
                df = pd.DataFrame(
                    {
                        "block_number": [1000],
                        "timestamp": [datetime.now()],
                        "value": [100],
                    }
                )

                result = sync.insert_data("test_contract", df)
                assert result is True
                mock_requests.assert_called_once()


@pytest.mark.slow
@pytest.mark.integration
def test_sync_historical_data():
    """Test historical data sync"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            with patch("requests.post") as mock_requests:
                # Mock responses for create_table and insert_data calls
                mock_requests.return_value.status_code = 200
                mock_requests.return_value.json.side_effect = [
                    {"success": False},  # First create_table call
                    {"rows_written": 5},  # First insert_data call
                    {"success": False},  # Second create_table call
                    {"rows_written": 5},  # Second insert_data call
                    {"success": False},  # Third create_table call
                    {"rows_written": 5},  # Third insert_data call
                    {"success": False},  # Fourth create_table call
                    {"rows_written": 5},  # Fourth insert_data call
                    {"success": False},  # Fifth create_table call
                    {"rows_written": 5},  # Fifth insert_data call
                    {"success": False},  # Sixth create_table call
                    {"rows_written": 5},  # Sixth insert_data call
                    {"success": False},  # Seventh create_table call
                    {"rows_written": 0},  # Seventh insert_data call (fails)
                    {"success": False},  # Eighth create_table call
                    {"rows_written": 0},  # Eighth insert_data call (fails)
                ]

                sync = DuneSync(asset="ETH")

                # Set a smaller block period to limit the number of iterations
                sync.block_period = 100

                # Create a mock Web3 instance
                mock_web3 = MagicMock()
                mock_web3.eth.block_number = 1000
                mock_web3.eth.contract.return_value = Mock()
                mock_web3.is_connected.return_value = True

                # Patch the get_web3 method
                sync.get_web3 = lambda: mock_web3
                sync.w3 = mock_web3

                # Mock the BlockchainDataCollector
                with patch("loop_dune.sync.BlockchainDataCollector") as mock_collector:
                    mock_collector_instance = MagicMock()
                    mock_collector_instance.get_contract_creation_block.return_value = (
                        100
                    )
                    mock_collector_instance.get_next_w3.return_value = mock_web3
                    mock_collector_instance.check_contract_creation_blocks.return_value = {
                        "test_contract": 100
                    }

                    # Create a larger DataFrame to ensure multiple API calls
                    df = pd.DataFrame(
                        {
                            "block_number": [1000, 1001, 1002, 1003, 1004],
                            "timestamp": [datetime.now()] * 5,
                            "value": [100, 101, 102, 103, 104],
                        }
                    )
                    mock_collector_instance.collect_contract_data.return_value = df
                    mock_collector.return_value = mock_collector_instance

                    sync.collector = mock_collector_instance
                    sync.sync_historical_data()
                    # We expect 18 calls total:
                    # - 9 create_table calls (blocks 100-900 in steps of 100)
                    # - 9 insert_data calls (one for each create_table)
                    assert mock_requests.call_count == 18


@pytest.mark.integration
def test_sync_historical_data_error_handling():
    """Test error handling during historical data sync"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            with patch("requests.post") as mock_requests:
                # Mock API error responses
                mock_requests.return_value.status_code = 500
                mock_requests.return_value.json.return_value = {
                    "error": "Internal Server Error"
                }

                sync = DuneSync(asset="ETH")
                sync.block_period = 100

                # Create a mock Web3 instance
                mock_web3 = MagicMock()
                mock_web3.eth.block_number = 1000
                mock_web3.eth.contract.return_value = Mock()
                mock_web3.is_connected.return_value = True

                sync.get_web3 = lambda: mock_web3
                sync.w3 = mock_web3

                with patch("loop_dune.sync.BlockchainDataCollector") as mock_collector:
                    mock_collector_instance = MagicMock()
                    mock_collector_instance.get_contract_creation_block.return_value = (
                        100
                    )
                    mock_collector_instance.get_next_w3.return_value = mock_web3
                    mock_collector_instance.check_contract_creation_blocks.return_value = {
                        "test_contract": 100
                    }
                    mock_collector_instance.collect_contract_data.return_value = (
                        pd.DataFrame(
                            {
                                "block_number": [1000],
                                "timestamp": [datetime.now()],
                                "value": [100],
                            }
                        )
                    )
                    mock_collector.return_value = mock_collector_instance

                    sync.collector = mock_collector_instance
                    sync.sync_historical_data()
                    # Verify that the error was handled gracefully
                    assert mock_requests.call_count > 0


@pytest.mark.integration
def test_sync_historical_data_empty():
    """Test historical data sync with empty data"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            with patch("requests.post") as mock_requests:
                mock_requests.return_value.status_code = 200
                mock_requests.return_value.json.return_value = {"success": True}

                sync = DuneSync(asset="ETH")
                sync.block_period = 100

                # Create a mock Web3 instance
                mock_web3 = MagicMock()
                mock_web3.eth.block_number = 1000
                mock_web3.eth.contract.return_value = Mock()
                mock_web3.is_connected.return_value = True

                sync.get_web3 = lambda: mock_web3
                sync.w3 = mock_web3

                with patch("loop_dune.sync.BlockchainDataCollector") as mock_collector:
                    mock_collector_instance = MagicMock()
                    mock_collector_instance.get_contract_creation_block.return_value = (
                        100
                    )
                    mock_collector_instance.get_next_w3.return_value = mock_web3
                    mock_collector_instance.check_contract_creation_blocks.return_value = {
                        "test_contract": 100
                    }
                    # Return empty DataFrame
                    mock_collector_instance.collect_contract_data.return_value = (
                        pd.DataFrame()
                    )
                    mock_collector.return_value = mock_collector_instance

                    sync.collector = mock_collector_instance
                    sync.sync_historical_data()
                    # Verify that no API calls were made for empty data
                    assert mock_requests.call_count == 0


@pytest.mark.integration
def test_sync_daily_data():
    """Test daily data sync"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            with patch("requests.post") as mock_requests:
                mock_requests.return_value.status_code = 200
                mock_requests.return_value.json.return_value = {"success": True}

                sync = DuneSync(asset="ETH")

                # Create a mock Web3 instance
                mock_web3 = MagicMock()
                mock_web3.eth.block_number = 1000
                mock_web3.eth.contract.return_value = Mock()
                mock_web3.is_connected.return_value = True

                # Patch the get_web3 method
                sync.get_web3 = lambda: mock_web3
                sync.w3 = mock_web3

                # Mock the BlockchainDataCollector
                with patch("loop_dune.sync.BlockchainDataCollector") as mock_collector:
                    mock_collector_instance = MagicMock()
                    mock_collector_instance.get_next_w3.return_value = mock_web3
                    mock_collector_instance.collect_contract_data.return_value = (
                        pd.DataFrame(
                            {
                                "block_number": [1000],
                                "timestamp": [datetime.now()],
                                "value": [100],
                            }
                        )
                    )
                    mock_collector.return_value = mock_collector_instance

                    sync.collector = mock_collector_instance
                    sync.sync_daily_data()
                    assert mock_requests.call_count >= 1


def test_invalid_asset():
    """Test initialization with invalid asset"""
    with pytest.raises(ValueError):
        DuneSync(asset="INVALID")


@pytest.mark.integration
def test_api_error_handling():
    """Test error handling for API failures"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            with patch("requests.post") as mock_requests:
                mock_requests.return_value.status_code = 400
                mock_requests.return_value.json.return_value = {"error": "Bad Request"}

                sync = DuneSync(asset="ETH")
                df = pd.DataFrame(
                    {
                        "block_number": [1000],
                        "timestamp": [datetime.now()],
                        "value": [100],
                    }
                )

                result = sync.create_table("test_contract", df)
                assert result is False


@pytest.mark.web3
def test_web3_connection_error():
    """Test handling of Web3 connection errors"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=False):
            with pytest.raises(ConnectionError):
                DuneSync(asset="ETH")


@pytest.mark.integration
def test_data_validation():
    """Test data validation before upload"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            with patch("requests.post") as mock_requests:
                sync = DuneSync(asset="ETH")
                # Test with empty DataFrame
                df = pd.DataFrame()
                result = sync.insert_data("test_contract", df)
                assert result is False
                mock_requests.assert_not_called()
