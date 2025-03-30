import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime

from loop_dune.sync import DuneSync
from loop_dune.collector import BlockchainDataCollector


@pytest.fixture
def mock_web3():
    with patch("web3.Web3") as mock:
        mock_instance = Mock()
        mock_instance.eth.block_number = 1000
        mock_instance.eth.contract.return_value = Mock()
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
            with patch("web3.Web3.eth.get_block_number", return_value=1000):
                with patch("requests.post") as mock_requests:
                    mock_requests.return_value.status_code = 200
                    mock_requests.return_value.json.return_value = {"success": True}

                    sync = DuneSync(asset="ETH")
                    with patch.object(sync, "get_web3") as mock_get_web3:
                        mock_web3 = MagicMock()
                        mock_web3.eth.block_number = 1000
                        mock_get_web3.return_value = mock_web3
                        sync.sync_historical_data()
                        assert mock_requests.call_count >= 2


@pytest.mark.integration
def test_sync_daily_data():
    """Test daily data sync"""
    with patch("web3.Web3.HTTPProvider") as mock_provider:
        with patch("web3.Web3.is_connected", return_value=True):
            with patch("web3.Web3.eth.get_block_number", return_value=1000):
                with patch("requests.post") as mock_requests:
                    mock_requests.return_value.status_code = 200
                    mock_requests.return_value.json.return_value = {"success": True}

                    sync = DuneSync(asset="ETH")
                    with patch.object(sync, "get_web3") as mock_get_web3:
                        mock_web3 = MagicMock()
                        mock_web3.eth.block_number = 1000
                        mock_get_web3.return_value = mock_web3
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
