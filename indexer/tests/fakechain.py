"""An in-memory EVM-ish JSON-RPC endpoint for tests, served via ``httpx.MockTransport``.

Supports exactly what the indexer uses: block headers, ``eth_chainId``,
``eth_getCode``, ``eth_call`` (direct, and through Multicall3 ``aggregate3``).
Contract state is a pure function of the block number, so tests can assert exact
values at any point in time.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from eth_abi import decode, encode
from eth_utils import to_checksum_address

from loop_indexer.chain.abi import get_function, load_abi
from loop_indexer.chain.multicall import MULTICALL3_ADDRESS

Handler = Callable[..., Any]  # (block, *args) -> value


class RevertedError(Exception):
    pass


@dataclass
class FakeContract:
    address: str
    deployed_block: int
    abi: str
    handlers: dict[str, Handler] = field(default_factory=dict)

    def call(self, data: bytes, block: int) -> bytes:
        selector, payload = data[:4], data[4:]
        for item in load_abi(self.abi):
            if item.get("type") != "function" or item["name"] not in self.handlers:
                continue
            fn = get_function(self.abi, item["name"], len(item.get("inputs", [])))
            if fn.selector == selector:
                args = decode(list(fn.input_types), payload) if fn.input_types else ()
                value = self.handlers[item["name"]](block, *args)
                values = value if isinstance(value, tuple) else (value,)
                return encode(list(fn.output_types), list(values))
        raise RevertedError(f"no handler for selector {selector.hex()} on {self.address}")


class FakeChain:
    def __init__(self, chain_id: int, timestamps: list[int]) -> None:
        self.chain_id = chain_id
        self.timestamps = timestamps  # index == block number
        self.contracts: dict[str, FakeContract] = {}
        self.requests: list[str] = []
        #: Return one of these HTTP statuses for the next N requests (failover tests).
        self.fail_next: list[int] = []

    @property
    def head(self) -> int:
        return len(self.timestamps) - 1

    def add(self, contract: FakeContract) -> FakeContract:
        self.contracts[to_checksum_address(contract.address)] = contract
        return contract

    # ------------------------------------------------------------------ rpc

    def _call(self, to: str, data: bytes, block: int) -> bytes:
        to = to_checksum_address(to)
        if to == MULTICALL3_ADDRESS:
            return self._aggregate3(data, block)
        contract = self.contracts.get(to)
        if contract is None or block < contract.deployed_block:
            return b""  # calling an address without code returns empty data
        return contract.call(data, block)

    def _aggregate3(self, data: bytes, block: int) -> bytes:
        (calls,) = decode(["(address,bool,bytes)[]"], data[4:])
        results = []
        for target, _allow_failure, calldata in calls:
            try:
                results.append((True, self._call(target, bytes(calldata), block)))
            except RevertedError:
                results.append((False, b""))
        return encode(["(bool,bytes)[]"], [results])

    def _block(self, tag: str) -> int:
        return self.head if tag == "latest" else int(tag, 16)

    def handle(self, method: str, params: list[Any]) -> Any:
        self.requests.append(method)
        if method == "eth_chainId":
            return hex(self.chain_id)
        if method == "eth_blockNumber":
            return hex(self.head)
        if method == "eth_getBlockByNumber":
            n = self._block(params[0])
            if n > self.head:
                return None
            return {"number": hex(n), "timestamp": hex(self.timestamps[n])}
        if method == "eth_getCode":
            contract = self.contracts.get(to_checksum_address(params[0]))
            deployed = contract is not None and self._block(params[1]) >= contract.deployed_block
            return "0x6000" if deployed else "0x"
        if method == "eth_call":
            data = bytes.fromhex(params[0]["data"].removeprefix("0x"))
            return "0x" + self._call(params[0]["to"], data, self._block(params[1])).hex()
        raise ValueError(f"unsupported method {method}")

    def _respond(self, item: dict[str, Any]) -> dict[str, Any]:
        try:
            return {"jsonrpc": "2.0", "id": item["id"],
                    "result": self.handle(item["method"], item["params"])}  # fmt: skip
        except RevertedError as exc:
            return {"jsonrpc": "2.0", "id": item["id"],
                    "error": {"code": 3, "message": f"execution reverted: {exc}"}}  # fmt: skip

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            if self.fail_next:
                return httpx.Response(self.fail_next.pop(0), text="unavailable")
            body = json.loads(request.content)
            if isinstance(body, list):
                return httpx.Response(200, json=[self._respond(i) for i in body])
            return httpx.Response(200, json=self._respond(body))

        return httpx.MockTransport(handler)


def linear_timestamps(start: int, blocks: int, block_time: int) -> list[int]:
    return [start + i * block_time for i in range(blocks)]
