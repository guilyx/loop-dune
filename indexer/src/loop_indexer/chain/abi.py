"""ABI helpers: resolve a function from a bundled ABI file and encode/decode calls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from eth_abi import decode, encode
from eth_utils import function_signature_to_4byte_selector


def _canonical_type(param: dict[str, Any]) -> str:
    """Canonical ABI type, expanding tuples (``tuple[]`` -> ``(a,b)[]``)."""
    kind: str = param["type"]
    if kind.startswith("tuple"):
        inner = ",".join(_canonical_type(c) for c in param["components"])
        return f"({inner}){kind[len('tuple') :]}"
    return kind


@dataclass(frozen=True)
class ContractFunction:
    name: str
    input_types: tuple[str, ...]
    output_types: tuple[str, ...]

    @property
    def signature(self) -> str:
        return f"{self.name}({','.join(self.input_types)})"

    @property
    def selector(self) -> bytes:
        return bytes(function_signature_to_4byte_selector(self.signature))

    def encode(self, *args: Any) -> bytes:
        if len(args) != len(self.input_types):
            raise TypeError(f"{self.signature} expects {len(self.input_types)} args")
        return self.selector + encode(list(self.input_types), list(args))

    def decode(self, data: bytes) -> tuple[Any, ...]:
        return tuple(decode(list(self.output_types), data))


@cache
def load_abi(name: str) -> tuple[dict[str, Any], ...]:
    """Load ``loop_indexer/abis/<name>.json``."""
    text = resources.files("loop_indexer.abis").joinpath(f"{name}.json").read_text()
    return tuple(json.loads(text))


@cache
def get_function(abi_name: str, function_name: str, arity: int | None = None) -> ContractFunction:
    matches = [
        item
        for item in load_abi(abi_name)
        if item.get("type") == "function"
        and item.get("name") == function_name
        and (arity is None or len(item.get("inputs", [])) == arity)
    ]
    if not matches:
        raise KeyError(f"{function_name} not found in ABI {abi_name!r}")
    if len(matches) > 1:
        raise KeyError(f"{function_name} is overloaded in ABI {abi_name!r}; pass arity")
    item = matches[0]
    return ContractFunction(
        name=function_name,
        input_types=tuple(_canonical_type(p) for p in item.get("inputs", [])),
        output_types=tuple(_canonical_type(p) for p in item.get("outputs", [])),
    )
