"""Structured logging: JSON lines in CI/containers, readable output in a terminal."""

from __future__ import annotations

import logging
import sys
from typing import Any, TextIO, cast

import structlog


class _LazyStderr:
    """Resolve ``sys.stderr`` at write time (it may be swapped, e.g. by test runners)."""

    def write(self, text: str) -> Any:
        return sys.stderr.write(text)

    def flush(self) -> None:
        sys.stderr.flush()


def configure_logging(level: str = "INFO", fmt: str = "auto") -> None:
    use_json = fmt == "json" or (fmt == "auto" and not sys.stderr.isatty())
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=cast(TextIO, _LazyStderr())),
        cache_logger_on_first_use=False,
    )
