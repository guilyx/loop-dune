"""Minimal JSON-RPC client with endpoint failover, retries and batching.

We deliberately avoid web3.py: the indexer only needs ``eth_call``, block headers and
``eth_getCode``. A small client over ``httpx`` is easier to reason about, cheap to
test with ``httpx.MockTransport`` and gives us full control over retry semantics.
"""

from __future__ import annotations

import itertools
import random
import threading
import time
from collections.abc import Sequence
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

# HTTP statuses worth retrying on another endpoint.
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 524, 525}


class RpcError(Exception):
    """The RPC request failed after exhausting retries on every endpoint."""


class CallRevertedError(RpcError):
    """A call reverted. Deterministic: retrying on another endpoint will not help."""


def _is_revert(error: dict[str, Any]) -> bool:
    message = str(error.get("message", "")).lower()
    return error.get("code") == 3 or "revert" in message


class RpcClient:
    """JSON-RPC over HTTP with sticky endpoint selection and failover.

    * Requests go to the current endpoint until it fails, then rotate.
    * Transport errors, retryable HTTP statuses and non-revert JSON-RPC errors
      (rate limits, "missing trie node" on non-archive nodes, ...) are retried with
      exponential backoff and jitter, rotating endpoints between attempts.
    * Reverts are raised immediately as :class:`CallRevertedError`.
    """

    def __init__(
        self,
        urls: Sequence[str],
        *,
        name: str = "rpc",
        timeout: float = 30.0,
        max_retries: int = 6,
        backoff_base: float = 0.5,
        backoff_max: float = 20.0,
        max_batch_size: int = 20,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        cleaned = [u.strip() for u in urls if u and u.strip()]
        if not cleaned:
            raise ValueError(f"{name}: at least one RPC URL is required")
        self.name = name
        self._urls = cleaned
        self._current = 0
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self.max_batch_size = max_batch_size
        self._http = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={"content-type": "application/json", "user-agent": "loop-indexer/1.0"},
        )

    # ------------------------------------------------------------------ plumbing

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> RpcClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def endpoint_count(self) -> int:
        return len(self._urls)

    def _endpoint(self) -> tuple[int, str]:
        with self._lock:
            return self._current, self._urls[self._current]

    def _rotate(self, failed_index: int) -> None:
        with self._lock:
            if self._current == failed_index:
                self._current = (self._current + 1) % len(self._urls)

    def _sleep(self, attempt: int) -> None:
        delay = min(self._backoff_max, self._backoff_base * (2**attempt))
        time.sleep(delay * (0.5 + random.random() / 2))  # noqa: S311 - jitter, not crypto

    def _post(self, payload: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            index, url = self._endpoint()
            try:
                response = self._http.post(url, json=payload)
                if response.status_code in _RETRYABLE_STATUS:
                    raise RpcError(f"HTTP {response.status_code}")
                response.raise_for_status()
                body = response.json()
                _raise_for_rpc_errors(body)
                return body
            except CallRevertedError:
                raise
            except (httpx.HTTPError, RpcError, ValueError) as exc:
                last_error = exc
                log.warning(
                    "rpc.retry",
                    rpc=self.name,
                    endpoint=index,
                    attempt=attempt + 1,
                    error=str(exc)[:200],
                )
                self._rotate(index)
                if attempt < self._max_retries:
                    self._sleep(attempt)
        raise RpcError(f"{self.name}: request failed after retries: {last_error}")

    # ------------------------------------------------------------------ requests

    def request(self, method: str, params: list[Any]) -> Any:
        body = self._post(
            {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        )
        return body["result"]

    def batch(self, calls: Sequence[tuple[str, list[Any]]]) -> list[Any]:
        """Send calls as JSON-RPC batches; results are returned in input order."""
        results: list[Any] = []
        for start in range(0, len(calls), self.max_batch_size):
            chunk = calls[start : start + self.max_batch_size]
            payload = [
                {"jsonrpc": "2.0", "id": i, "method": method, "params": params}
                for i, (method, params) in enumerate(chunk)
            ]
            body = self._post(payload)
            by_id = {item["id"]: item["result"] for item in body}
            results.extend(by_id[i] for i in range(len(chunk)))
        return results

    # ------------------------------------------------------------------ helpers

    def block_number(self) -> int:
        return int(self.request("eth_blockNumber", []), 16)

    def block_timestamps(self, numbers: Sequence[int]) -> dict[int, int]:
        headers = self.batch([("eth_getBlockByNumber", [hex(n), False]) for n in numbers])
        out: dict[int, int] = {}
        for number, header in zip(numbers, headers, strict=True):
            if header is None:
                raise RpcError(f"{self.name}: block {number} not found")
            out[number] = int(header["timestamp"], 16)
        return out

    def latest_block(self) -> tuple[int, int]:
        header = self.request("eth_getBlockByNumber", ["latest", False])
        return int(header["number"], 16), int(header["timestamp"], 16)

    def eth_call(self, to: str, data: bytes, block: int | str = "latest") -> bytes:
        tag = hex(block) if isinstance(block, int) else block
        result = self.request("eth_call", [{"to": to, "data": "0x" + data.hex()}, tag])
        return bytes.fromhex(result.removeprefix("0x"))

    def get_code(self, address: str, block: int | str = "latest") -> bytes:
        tag = hex(block) if isinstance(block, int) else block
        result = self.request("eth_getCode", [address, tag])
        return bytes.fromhex(result.removeprefix("0x"))


def _raise_for_rpc_errors(body: Any) -> None:
    items = body if isinstance(body, list) else [body]
    for item in items:
        error = item.get("error") if isinstance(item, dict) else None
        if error:
            if _is_revert(error):
                raise CallRevertedError(str(error.get("message")))
            raise RpcError(f"JSON-RPC error {error.get('code')}: {error.get('message')}")
        if not isinstance(item, dict) or "result" not in item:
            raise RpcError(f"malformed JSON-RPC response: {str(item)[:200]}")
