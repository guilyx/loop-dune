"""Contract configurations for Spectra Protocol."""

from typing import Dict, Any
import json
import os

# Contract configurations for different assets
CONTRACTS = {
    "ETH": {
        "chain_id": "1",
        "balances": [
            {
                "contract_address": "0x9BfCD3788f923186705259ae70A1192F601BeB47",  # yneth CDP Vault
                "token_address": "0x2408569177553A427dd6956E1717f2fBE1a96F1D",  # WETH
                "name": "ynETH CDP Balance",
                "description": "ynETH balance in CDP Vault",
            },
            {
                "contract_address": "0x9c5EE26b9623cA864693C575a8fBc8933ae964E7",  # ynethx CDP Vault
                "token_address": "0xbc48c48789031a130f957c59e07b7f987aa642de",  # WETH
                "name": "ynETHx CDP Vault WETH Balance",
                "description": "ynETHx balance in CDP Vault",
            },
        ],
        "eth_yneth_cdp_vault": {
            "name": "Spectra yneth CDP Vault",
            "address": "0x9BfCD3788f923186705259ae70A1192F601BeB47",
            "abi_file": "eth/cdp_vault_spectra.json",
            "functions_to_track": [
                {
                    "name": "spotPrice",
                    "params": [],
                    "column_names": ["spot_price"],
                },
            ],
        },
        "eth_ynethx_cdp_vault": {
            "name": "Spectra ynethx CDP Vault",
            "address": "0x9c5EE26b9623cA864693C575a8fBc8933ae964E7",
            "abi_file": "eth/cdp_vault_spectra.json",
            "functions_to_track": [
                {
                    "name": "spotPrice",
                    "params": [],
                    "column_names": ["spot_price"],
                },
            ],
        },
        "lp_eth_pool": {
            "name": "LP-ETH Pool",
            "address": "0xa684EAf215ad323452e2B2bF6F817d4aa5C116ab",
            "abi_file": "eth/lpeth.json",
            "functions_to_track": [
                {
                    "name": "totalBorrowed",
                    "params": [],
                    "column_names": ["total_borrowed"],
                },
                {
                    "name": "baseInterestRate",
                    "params": [],
                    "column_names": ["base_interest_rate"],
                },
                {
                    "name": "supplyRate",
                    "params": [],
                    "column_names": ["supply_rate"],
                },
                {
                    "name": "availableLiquidity",
                    "params": [],
                    "column_names": ["available_liquidity"],
                },
                {
                    "name": "expectedLiquidity",
                    "params": [],
                    "column_names": ["expected_liquidity"],
                },
                {
                    "name": "totalSupply",
                    "params": [],
                    "column_names": ["total_supply"],
                },
                {
                    "name": "balanceOf",
                    "params": [
                        "0x110f00b890102A7534484db8b3C5695Bd49De27b"
                    ],  # Locked LP-ETH contract address
                    "column_names": ["locked_lp_eth_balance"],
                },
                {
                    "name": "creditManagerBorrowed",
                    "params": [
                        "0x9BfCD3788f923186705259ae70A1192F601BeB47"  # spectraCDP address
                    ],
                    "column_names": ["credit_manager_borrowed"],
                },
                {
                    "name": "creditManagerDebtLimit",
                    "params": [
                        "0x9BfCD3788f923186705259ae70A1192F601BeB47"  # spectraCDP address
                    ],
                    "column_names": ["credit_manager_debt_limit"],
                },
                {
                    "name": "creditManagerBorrowable",
                    "params": [
                        "0x9BfCD3788f923186705259ae70A1192F601BeB47"  # spectraCDP address
                    ],
                    "column_names": ["credit_manager_borrowable"],
                },
            ],
        },
        "slp_eth": {
            "name": "SLP-ETH",
            "address": "0x3976d71e7DdFBaB9bD120Ec281B7d35fa0F28528",
            "abi_file": "eth/staked_lpeth.json",
            "functions_to_track": [
                {
                    "name": "totalSupply",
                    "params": [],
                    "column_names": ["total_supply"],
                },
            ],
        },
        # "spectra_lp": {
        #     "name": "Spectra LP",
        #     "address": "0x2408569177553A427dd6956E1717f2fBE1a96F1D",
        #     "abi_file": "eth/yneth_spectra_lp.json",
        #     "functions_to_track": [
        #         {
        #             "name": "balanceOf",
        #             "params": [
        #                 "0x9BfCD3788f923186705259ae70A1192F601BeB47"
        #             ],  # CDP Vault address
        #             "column_names": ["balance"],
        #         },
        #     ],
        # },
    },
    "USD": {
        "chain_id": "1",
        "balances": [
            {
                "contract_address": "0xbb23b7ACdE2B3A2E6446B16Cd3Dd471b0d80342c",  # DEUSD CDP Vault
                "token_address": "0x09d484B738dD85CE3953102453E91507982121d0",  # DAI
                "name": "Loop DEUSD CDP Balance",
                "description": "DEUSD balance in CDP Vault",
            }
        ],
        "usd_cdp_vault": {
            "name": "DEUSD CDP Vault",
            "address": "0xbb23b7ACdE2B3A2E6446B16Cd3Dd471b0d80342c",
            "abi_file": "eth/cdp_vault_spectra.json",  # Same ABI as ETH CDP
            "functions_to_track": [
                {
                    "name": "spotPrice",
                    "params": [],
                    "column_names": ["spot_price"],
                },
            ],
        },
        "lp_usd_pool": {
            "name": "LP-USD Pool",
            "address": "0x0eecBDbF7331B8a50FCd0Bf2C267Bf47BD876054",
            "abi_file": "eth/lpeth.json",  # Same ABI as ETH pool
            "functions_to_track": [
                {
                    "name": "totalBorrowed",
                    "params": [],
                    "column_names": ["total_borrowed"],
                },
                {
                    "name": "baseInterestRate",
                    "params": [],
                    "column_names": ["base_interest_rate"],
                },
                {
                    "name": "supplyRate",
                    "params": [],
                    "column_names": ["supply_rate"],
                },
                {
                    "name": "availableLiquidity",
                    "params": [],
                    "column_names": ["available_liquidity"],
                },
                {
                    "name": "expectedLiquidity",
                    "params": [],
                    "column_names": ["expected_liquidity"],
                },
                {
                    "name": "totalSupply",
                    "params": [],
                    "column_names": ["total_supply"],
                },
                {
                    "name": "balanceOf",
                    "params": [
                        "0xACA47DE7910FD8f108B147d69ADDBaC6Cc18966E"
                    ],  # Locked LP-USD contract address
                    "column_names": ["locked_lp_usd_balance"],
                },
                {
                    "name": "creditManagerBorrowed",
                    "params": [
                        "0xbb23b7ACdE2B3A2E6446B16Cd3Dd471b0d80342c"  # deusdCDP address
                    ],
                    "column_names": ["credit_manager_borrowed"],
                },
                {
                    "name": "creditManagerDebtLimit",
                    "params": [
                        "0xbb23b7ACdE2B3A2E6446B16Cd3Dd471b0d80342c"  # deusdCDP address
                    ],
                    "column_names": ["credit_manager_debt_limit"],
                },
                {
                    "name": "creditManagerBorrowable",
                    "params": [
                        "0xbb23b7ACdE2B3A2E6446B16Cd3Dd471b0d80342c"  # deusdCDP address
                    ],
                    "column_names": ["credit_manager_borrowable"],
                },
            ],
        },
        "slp_usd": {
            "name": "SLP-USD",
            "address": "0xBFB53910C935E837C74e6C4EF584557352d20fDe",
            "abi_file": "eth/staked_lpeth.json",  # Same ABI as SLP-ETH
            "functions_to_track": [
                {
                    "name": "totalSupply",
                    "params": [],
                    "column_names": ["total_supply"],
                },
            ],
        },
    },
    "BNB": {
        "chain_id": "56",
        "balances": [
            {
                "contract_address": "0x03C07e6d561b664246058974dB31dbF1c1C0B416",  # clisBNB CDP Vault
                "token_address": "0x1d9d27f0b89181cf1593ac2b36a37b444eb66bee",  # WBNB
                "name": "clisBNB CDP Balance",
                "description": "clisBNB balance in CDP Vault",
            }
        ],
        "bnb_cdp_vault": {
            "name": "clisBNB CDP Vault",
            "address": "0x03C07e6d561b664246058974dB31dbF1c1C0B416",
            "abi_file": "eth/cdp_vault_spectra.json",  # Same ABI as ETH CDP
            "functions_to_track": [
                {
                    "name": "spotPrice",
                    "params": [],
                    "column_names": ["spot_price"],
                },
            ],
        },
        "lp_bnb_pool": {
            "name": "LP-BNB Pool",
            "address": "0xed166436559fd3d7f44cb00cacda96eb999d789e",
            "abi_file": "eth/lpeth.json",  # Same ABI as ETH pool
            "functions_to_track": [
                {
                    "name": "totalBorrowed",
                    "params": [],
                    "column_names": ["total_borrowed"],
                },
                {
                    "name": "baseInterestRate",
                    "params": [],
                    "column_names": ["base_interest_rate"],
                },
                {
                    "name": "supplyRate",
                    "params": [],
                    "column_names": ["supply_rate"],
                },
                {
                    "name": "availableLiquidity",
                    "params": [],
                    "column_names": ["available_liquidity"],
                },
                {
                    "name": "expectedLiquidity",
                    "params": [],
                    "column_names": ["expected_liquidity"],
                },
                {
                    "name": "totalSupply",
                    "params": [],
                    "column_names": ["total_supply"],
                },
                {
                    "name": "balanceOf",
                    "params": [
                        "0x7Cdd4fc8715e5A45E0f9424b7D0e630E1aCF5BC4"
                    ],  # Locked LP-USD contract address
                    "column_names": ["locked_lp_bnb_balance"],
                },
                {
                    "name": "creditManagerBorrowed",
                    "params": [
                        "0xbb23b7ACdE2B3A2E6446B16Cd3Dd471b0d80342c"  # deusdCDP address
                    ],
                    "column_names": ["credit_manager_borrowed"],
                },
                {
                    "name": "creditManagerDebtLimit",
                    "params": [
                        "0xbb23b7ACdE2B3A2E6446B16Cd3Dd471b0d80342c"  # deusdCDP address
                    ],
                    "column_names": ["credit_manager_debt_limit"],
                },
                {
                    "name": "creditManagerBorrowable",
                    "params": [
                        "0xbb23b7ACdE2B3A2E6446B16Cd3Dd471b0d80342c"  # deusdCDP address
                    ],
                    "column_names": ["credit_manager_borrowable"],
                },
            ],
        },
        "slp_bnb": {
            "name": "SLP-BNB",
            "address": "0x76a173580ac0456fd208a593722998d6b5b7063d",
            "abi_file": "eth/staked_lpeth.json",  # Same ABI as SLP-ETH
            "functions_to_track": [
                {
                    "name": "totalSupply",
                    "params": [],
                    "column_names": ["total_supply"],
                },
            ],
        },
    },
}


def load_abi(contract_name: str, asset: str) -> Dict:
    """
    Load ABI from JSON file.

    Args:
        contract_name: Name of the contract in CONTRACTS dict
        asset: Asset type (ETH or USD)

    Returns:
        Contract ABI as dictionary
    """
    contract = CONTRACTS[asset][contract_name]
    abi_path = os.path.join(os.path.dirname(__file__), "abis", contract["abi_file"])
    try:
        with open(abi_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"ABI file {contract['abi_file']} not found for contract {contract_name}"
        )


# Load ABIs at module import time
for asset in ["ETH", "USD", "BNB"]:
    for contract_name in CONTRACTS[asset]:
        if contract_name == "chain_id":
            continue
        CONTRACTS[asset][contract_name]["abi"] = load_abi(contract_name, asset)
