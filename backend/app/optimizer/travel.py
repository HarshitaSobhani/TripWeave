"""Travel model: the only place that turns matrix data into scheduling numbers.

Rules that keep the optimizer honest:
* routed matrix  -> minutes = ceil(duration_s / 60); basis "routed".
* straight-line  -> distances are great-circle estimates used ONLY as an ordering
  cost proxy. Scheduling uses the user's transit buffer, basis "user_buffer".
"""

from __future__ import annotations

from math import ceil

from .domain import UNREACHABLE_MIN, TravelMatrix


class TravelModel:
    def __init__(self, matrix: TravelMatrix, buffer_minutes: int, max_leg_minutes: int | None = None) -> None:
        self.matrix = matrix
        self.buffer = buffer_minutes
        self.max_leg = max_leg_minutes if matrix.routed else None

    @property
    def routed(self) -> bool:
        return self.matrix.routed

    def _pair(self, a: str, b: str) -> tuple[int, int]:
        return self.matrix.idx(a), self.matrix.idx(b)

    def minutes(self, a: str, b: str) -> int:
        if a == b:
            return 0
        i, j = self._pair(a, b)
        if not self.routed:
            return self.buffer
        assert self.matrix.durations_s is not None
        d = self.matrix.durations_s[i][j]
        if d is None:
            return UNREACHABLE_MIN
        raw = ceil(d / 60.0)
        if self.max_leg is not None and raw > self.max_leg:
            return UNREACHABLE_MIN
        return raw + self.buffer

    def reachable(self, a: str, b: str) -> bool:
        return self.minutes(a, b) < UNREACHABLE_MIN

    def distance(self, a: str, b: str) -> float | None:
        if a == b:
            return 0.0
        i, j = self._pair(a, b)
        return self.matrix.distances_m[i][j]

    def cost(self, a: str, b: str) -> int:
        """Integer arc cost: routed minutes, or straight-line metres (proxy)."""
        if a == b:
            return 0
        if self.routed:
            return self.minutes(a, b)
        d = self.distance(a, b)
        return round(d) if d is not None else UNREACHABLE_MIN * 100

    @property
    def basis(self) -> str:
        return "routed" if self.routed else "user_buffer"

    @property
    def distance_kind(self) -> str:
        return self.matrix.kind
