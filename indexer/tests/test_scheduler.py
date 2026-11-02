from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from loop_indexer.scheduler import Heartbeat, Scheduler, Step, next_slot, refresh_dashboard

H = timedelta(hours=1)
M = timedelta(minutes=1)


def at(hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(2026, 1, 1, hh, mm, ss, tzinfo=UTC)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (at(10, 0), at(10, 17)),
        (at(10, 16, 59), at(10, 17)),
        (at(10, 17), at(11, 17)),  # strictly after now
        (at(10, 30), at(11, 17)),
        (at(23, 50), datetime(2026, 1, 2, 0, 17, tzinfo=UTC)),
    ],
)
def test_next_slot(now: datetime, expected: datetime) -> None:
    assert next_slot(now, H, 17 * M) == expected


def test_next_slot_daily() -> None:
    assert next_slot(at(4, 0), timedelta(days=1), 3 * H + 17 * M) == datetime(
        2026, 1, 2, 3, 17, tzinfo=UTC
    )


class Recorder:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(f"{request.url.path} {request.content.decode()}")
            return httpx.Response(200)

        return httpx.MockTransport(handler)


def test_cycle_isolates_failures_and_pings_heartbeat() -> None:
    calls: list[str] = []

    def boom() -> None:
        calls.append("export")
        raise RuntimeError("dune down")

    rec = Recorder()
    scheduler = Scheduler(
        [
            Step("index", lambda: calls.append("index") is None),
            Step("export-dune", boom),
            Step("health", lambda: calls.append("health") is None and False),
        ],
        every=H,
        offset=17 * M,
        heartbeat=Heartbeat("https://hc.example/ping/abc", transport=rec.transport()),
    )
    result = scheduler.run_cycle()
    assert calls == ["index", "export", "health"]  # a failing step never skips the next
    assert not result.ok
    assert result.failed == ("export-dune", "health")
    assert rec.requests[0].startswith("/ping/abc/fail failed: export-dune, health")

    ok = Scheduler(
        [Step("index", lambda: None)],
        every=H,
        offset=17 * M,
        heartbeat=Heartbeat("https://hc.example/ping/abc/", transport=rec.transport()),
    ).run_cycle()
    assert ok.ok
    assert rec.requests[1].startswith("/ping/abc ok")


def test_heartbeat_is_optional_and_never_raises() -> None:
    Heartbeat(None).ping(True, "nothing to do")

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    Heartbeat("https://hc.example/x", transport=httpx.MockTransport(down)).ping(False, "x")


def test_run_forever_sleeps_until_next_slot_and_stops_gracefully() -> None:
    clock = {"now": at(10, 0)}
    runs: list[datetime] = []
    scheduler = Scheduler(
        [Step("index", lambda: runs.append(clock["now"]) is None)],
        every=H,
        offset=17 * M,
        heartbeat=Heartbeat(None),
        clock=lambda: clock["now"],
    )

    def fake_wait(timeout: float | None = None) -> bool:
        assert timeout == pytest.approx(17 * 60)  # 10:00 -> 10:17
        clock["now"] += timedelta(seconds=timeout or 0)
        return False

    scheduler._stop.wait = fake_wait  # type: ignore[method-assign]
    scheduler.run_forever(run_now=True, max_cycles=2)
    assert runs == [at(10, 0), at(10, 17)]


def test_stop_interrupts_the_wait() -> None:
    scheduler = Scheduler([Step("index", lambda: None)], every=H, offset=17 * M,
                          heartbeat=Heartbeat(None))  # fmt: skip
    thread = threading.Thread(target=scheduler.run_forever, kwargs={"run_now": False})
    thread.start()
    scheduler.stop()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert scheduler.cycles == 0


def test_offset_must_fit_in_interval() -> None:
    with pytest.raises(ValueError, match="offset"):
        Scheduler([], every=H, offset=H, heartbeat=Heartbeat(None))


def test_refresh_dashboard_sends_bearer_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"revalidated": True})

    url = "http://dashboard:3000/api/revalidate"
    assert refresh_dashboard(url, "s3cret", transport=httpx.MockTransport(handler))
    assert seen[0].method == "POST"
    assert seen[0].headers["authorization"] == "Bearer s3cret"


def test_refresh_dashboard_reports_rejection() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(401))
    assert not refresh_dashboard("http://dashboard/api/revalidate", "bad", transport=transport)
