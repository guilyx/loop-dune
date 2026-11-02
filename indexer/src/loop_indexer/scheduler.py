"""In-process scheduler for long-running hosts (a VPS, a container platform).

GitHub Actions and Kubernetes have their own cron; a plain server does not, and
system cron loses the container's environment and logs. `loop-indexer schedule`
runs the same steps as the hourly workflow on a fixed wall-clock grid:

    index -> export to Dune (if configured) -> freshness check -> heartbeat

Each step is isolated: a failing Dune export never stops the next hour's indexing.
After every cycle an optional heartbeat URL is pinged (healthchecks.io convention:
``<url>`` on success, ``<url>/fail`` on failure), so a dead-man's switch alerts you
when the host stops reporting, not only when a step fails.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from loop_indexer.timegrid import floor_to

log = structlog.get_logger(__name__)


def next_slot(now: datetime, every: timedelta, offset: timedelta) -> datetime:
    """First instant strictly after ``now`` on the grid ``k * every + offset``."""
    slot = floor_to(now - offset, every) + offset
    return slot if slot > now else slot + every


@dataclass(frozen=True)
class Step:
    name: str
    #: Runs the step; raising (or returning False) marks it failed.
    action: Callable[[], bool | None]


@dataclass(frozen=True)
class CycleResult:
    ok: bool
    failed: tuple[str, ...]
    seconds: float


class Heartbeat:
    """Ping a monitoring URL after each cycle. Never raises: monitoring is best effort."""

    def __init__(self, url: str | None, *, transport: httpx.BaseTransport | None = None) -> None:
        self.url = url.rstrip("/") if url else None
        self._http = httpx.Client(timeout=10.0, transport=transport) if self.url else None

    def ping(self, ok: bool, message: str) -> None:
        if not self.url or self._http is None:
            return
        target = self.url if ok else f"{self.url}/fail"
        try:
            self._http.post(target, content=message.encode()[:10_000])
        except httpx.HTTPError as exc:
            log.warning("heartbeat.failed", error=str(exc))

    def close(self) -> None:
        if self._http is not None:
            self._http.close()


class Scheduler:
    def __init__(
        self,
        steps: Sequence[Step],
        *,
        every: timedelta,
        offset: timedelta,
        heartbeat: Heartbeat,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        if offset >= every:
            raise ValueError("offset must be shorter than the interval")
        self.steps = list(steps)
        self.every = every
        self.offset = offset
        self.heartbeat = heartbeat
        self.clock = clock
        self._stop = threading.Event()
        self.cycles = 0

    def stop(self) -> None:
        """Request a graceful stop: the current step finishes, no new cycle starts."""
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def run_cycle(self) -> CycleResult:
        started = time.monotonic()
        failed: list[str] = []
        for step in self.steps:
            if self.stopping:
                break
            log.info("schedule.step", step=step.name)
            try:
                if step.action() is False:
                    failed.append(step.name)
            except Exception as exc:  # one failing step must never kill the loop
                log.exception("schedule.step_failed", step=step.name, error=str(exc))
                failed.append(step.name)
        result = CycleResult(not failed, tuple(failed), round(time.monotonic() - started, 1))
        self.cycles += 1
        summary = "ok" if result.ok else f"failed: {', '.join(result.failed)}"
        log.info("schedule.cycle", ok=result.ok, failed=list(result.failed), seconds=result.seconds)
        self.heartbeat.ping(result.ok, f"{summary} ({result.seconds}s)")
        return result

    def run_forever(self, *, run_now: bool = True, max_cycles: int | None = None) -> None:
        if run_now:
            self.run_cycle()
        while not self.stopping and (max_cycles is None or self.cycles < max_cycles):
            wake = next_slot(self.clock(), self.every, self.offset)
            log.info("schedule.sleep", until=wake.isoformat())
            # Event.wait returns early on stop(), so SIGTERM never waits up to an hour.
            if self._stop.wait(max(0.0, (wake - self.clock()).total_seconds())):
                break
            self.run_cycle()
        log.info("schedule.stopped", cycles=self.cycles)
