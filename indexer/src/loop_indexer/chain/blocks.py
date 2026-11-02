"""Resolve wall-clock timestamps to block numbers.

``block_at(ts)`` returns the *last block whose timestamp is <= ts*: the chain state
"as of" that instant. Snapshotting every chain on the same UTC grid is what makes
series from different chains (12s Ethereum blocks, sub-second BSC blocks) joinable.

Strategy: keep every block timestamp we have ever seen as an anchor, bracket the
target between the closest known blocks, guess the boundary from the local block
rate, then fetch a small *window* of headers around the guess in one JSON-RPC batch.
With a good guess the boundary falls inside the first window: ~1 round trip/hour.
If not, the window still narrows the bracket and we iterate (worst case: bisection).
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable

from loop_indexer.chain.rpc import RpcClient

# Minimum timestamp distance between two anchors used to estimate the block rate.
_SLOPE_MIN_SECONDS = 600
# Extra probes around each guess, in multiples of the window size.
_FENCES = (4, 32, 256)


class BlockResolver:
    def __init__(
        self,
        rpc: RpcClient,
        *,
        anchors: Iterable[tuple[int, int]] = (),
        window: int = 16,
    ) -> None:
        self._rpc = rpc
        self._window = max(2, window)
        self._blocks: list[int] = []  # sorted block numbers
        self._times: list[int] = []  # timestamps aligned with _blocks (non-decreasing)
        self._ts: dict[int, int] = {}
        self._latest: tuple[int, int] | None = None
        self.rpc_round_trips = 0
        self._add(dict(anchors))

    # ------------------------------------------------------------------ cache

    def _add(self, points: dict[int, int]) -> None:
        for block, ts in points.items():
            if block not in self._ts:
                idx = bisect.bisect_left(self._blocks, block)
                self._blocks.insert(idx, block)
                self._times.insert(idx, ts)
            self._ts[block] = ts

    def _fetch(self, blocks: list[int]) -> None:
        missing = [b for b in blocks if b not in self._ts]
        if missing:
            self.rpc_round_trips += 1
            self._add(self._rpc.block_timestamps(missing))

    def timestamp(self, block: int) -> int:
        self._fetch([block])
        return self._ts[block]

    def latest(self, *, refresh: bool = False) -> tuple[int, int]:
        if self._latest is None or refresh:
            self.rpc_round_trips += 1
            self._latest = self._rpc.latest_block()
            self._add({self._latest[0]: self._latest[1]})
        return self._latest

    # ------------------------------------------------------------------ search

    def _bracket(self, ts: int) -> tuple[int, int]:
        """Closest known blocks with ``t(lo) <= ts < t(hi)``."""
        latest_block, _ = self.latest()
        if 0 not in self._ts:
            self._fetch([0])
        # Timestamps are non-decreasing in block number, so the aligned timestamp
        # list is sorted and we can bisect it directly.
        idx = bisect.bisect_right(self._times, ts)
        lo = self._blocks[idx - 1] if idx > 0 else 0
        hi = self._blocks[idx] if idx < len(self._blocks) else latest_block
        return lo, hi

    def _rate(self, lo: int, hi: int) -> float:
        """Blocks per second near ``lo``, from the nearest anchor at least 10 min below."""
        t_lo = self._ts[lo]
        j = bisect.bisect_right(self._times, t_lo - _SLOPE_MIN_SECONDS) - 1
        if j >= 0 and self._blocks[j] < lo:
            b = self._blocks[j]
            return (lo - b) / (t_lo - self._ts[b])
        return (hi - lo) / max(1, self._ts[hi] - t_lo)

    def _guess(self, lo: int, hi: int, ts: int) -> int:
        t_lo, t_hi = self._ts[lo], self._ts[hi]
        if hi - lo <= self._window * _FENCES[-1] * 2 and t_hi > t_lo:
            # Tight bracket: the secant through its two ends is the best local estimate.
            return lo + round((ts - t_lo) * (hi - lo) / (t_hi - t_lo))
        return lo + round((ts - t_lo) * self._rate(lo, hi))

    def block_at(self, ts: int) -> int:
        latest_block, latest_ts = self.latest()
        if ts >= latest_ts:
            return latest_block
        lo, hi = self._bracket(ts)
        if self._ts[lo] > ts:
            raise ValueError(f"timestamp {ts} precedes genesis")
        bisect_next = False
        while hi - lo > 1:
            if hi - lo - 1 <= self._window:
                candidates = list(range(lo + 1, hi))
            else:
                # Safeguard: if the previous probes missed entirely, interpolation is not
                # trustworthy here (e.g. genesis timestamp 0, block-time changes), and a
                # bisection step guarantees the bracket shrinks geometrically.
                guess = (lo + hi) // 2 if bisect_next else self._guess(lo, hi, ts)
                # Centre the window on the guess, a little biased upwards so that the
                # first block *after* the boundary is likely included. Fence probes at
                # widening distances ride in the same batch: if the window misses
                # (block rates drift), the bracket still shrinks to a few hundred
                # blocks instead of falling back to bisecting towards the chain head.
                start = guess - self._window // 2 + 1
                start = min(max(lo + 1, start), hi - self._window)
                window = range(start, start + self._window)
                fences = (guess + sign * self._window * f for f in _FENCES for sign in (-1, 1))
                candidates = sorted({*window, *(c for c in fences if lo < c < hi)})
            self._fetch(candidates)
            before = (lo, hi)
            for b in candidates:
                if self._ts[b] <= ts:
                    lo = max(lo, b)
                else:
                    hi = min(hi, b)
                    break
            # The window contained the boundary iff it moved *both* ends.
            bisect_next = not (lo != before[0] and hi != before[1])
        return lo
