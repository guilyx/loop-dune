"""Runtime configuration, read from the environment (and an optional ``.env`` file)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://loop:loop@localhost:5432/loop"

    # Comma-separated RPC URLs. Each chain in the registry names its variable
    # (``rpc_urls_env``); these two cover the chains we ship.
    eth_rpc_urls: str = ""
    bsc_rpc_urls: str = ""
    rpc_timeout: float = 30.0
    rpc_max_retries: int = 6
    rpc_max_batch_size: int = 20

    #: Seconds behind the chain head we refuse to snapshot (reorg safety).
    finality_seconds: int = 900

    dune_api_key: SecretStr | None = None
    dune_namespace: str | None = None
    dune_table_prefix: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")] = "loop"
    dune_api_url: str = "https://api.dune.com/api/v1"

    migrations_dir: Path | None = None

    log_level: str = "INFO"
    log_format: Literal["auto", "json", "console"] = "auto"

    def rpc_urls(self, env_name: str) -> list[str]:
        raw = getattr(self, env_name.lower(), None) or os.environ.get(env_name, "")
        return [u.strip() for u in str(raw).split(",") if u.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
