from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from .hours import Windows

UNREACHABLE_MIN = 100_000


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float
    label: str = ""


@dataclass(frozen=True)
class Candidate:
    key: int
    name: str
    lat: float
    lon: float
    visit_minutes: int
    interest: int = 3  # 1..5
    mandatory: bool = False
    cost: Decimal | None = None  # per person
    cost_currency: str | None = None
    hours: Windows | None = None  # None = unknown
    pinned_day: int | None = None  # user constraint: must be on this day index
    locked_day: int | None = None  # manual edit: keep on this day
    locked_order: int | None = None  # manual edit: relative order within day
    category: str = ""


@dataclass(frozen=True)
class DayPlan:
    index: int
    date: date
    start: int  # minutes since midnight
    end: int

    @property
    def weekday(self) -> int:
        return self.date.weekday()


@dataclass
class TravelMatrix:
    """Pairwise travel data between `keys`.

    kind == "routed": `durations_s` and `distances_m` come from a routing service.
    kind == "straight_line_estimate": only `distances_m` (great-circle metres) is
    set; `durations_s` is None. Those distances are not routes and never become
    travel times.
    """

    keys: list[str]
    kind: Literal["routed", "straight_line_estimate"]
    distances_m: list[list[float | None]]
    durations_s: list[list[float | None]] | None = None
    provider: str = "straight_line"
    mode: str = "walking"
    fetched_at: str | None = None
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._idx = {k: i for i, k in enumerate(self.keys)}
        n = len(self.keys)
        if len(self.distances_m) != n or any(len(r) != n for r in self.distances_m):
            raise ValueError("distance matrix shape mismatch")
        if self.kind == "routed":
            d = self.durations_s
            if d is None or len(d) != n or any(len(r) != n for r in d):
                raise ValueError("routed matrix requires square durations")
        elif self.durations_s is not None:
            raise ValueError("straight-line matrix must not carry durations")

    @property
    def routed(self) -> bool:
        return self.kind == "routed"

    def idx(self, key: str) -> int:
        return self._idx[key]


@dataclass
class ProblemSpec:
    candidates: list[Candidate]
    days: list[DayPlan]
    travelers: int = 1
    budget: Decimal | None = None
    currency: str = "EUR"
    committed_spend: Decimal = Decimal("0")  # user-entered expenses already counted
    max_daily_minutes: int | None = None  # visit + travel, excludes waiting
    max_travel_minutes: int | None = None  # per day, enforced only with routing
    max_leg_minutes: int | None = None  # per single leg, enforced only with routing
    transit_buffer_minutes: int = 15  # user assumption between stops (not an estimate)
    start_point: Point | None = None
    end_point: Point | None = None
    interest_weight: float | None = None  # cost units per interest point
    balance_weight: float | None = None  # cost units per minute of day imbalance
    mode: str = "walking"

    def candidate(self, key: int) -> Candidate:
        for c in self.candidates:
            if c.key == key:
                return c
        raise KeyError(key)


@dataclass
class Issue:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    place_key: int | None = None
    day_index: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "place_key": self.place_key,
            "day_index": self.day_index,
        }


@dataclass
class ScheduledStop:
    key: int
    day_index: int
    position: int
    arrive: int
    start: int
    end: int
    wait: int
    travel_minutes: int | None  # minutes used for scheduling the leg into this stop
    travel_basis: str  # "routed" | "user_buffer" | "none"
    distance_m: float | None
    distance_kind: str | None  # "routed" | "straight_line_estimate"
    warnings: list[str] = field(default_factory=list)


@dataclass
class Unscheduled:
    key: int
    code: str
    detail: str


@dataclass
class DaySchedule:
    day_index: int
    date: date
    stops: list[ScheduledStop]
    visit_minutes: int
    travel_minutes: int
    wait_minutes: int
    distance_m: float
    distance_kind: str
    day_end_used: int


@dataclass
class OptimizationResult:
    status: Literal["feasible", "infeasible", "empty"]
    solver: str
    days: list[DaySchedule]
    unscheduled: list[Unscheduled]
    issues: list[Issue]
    explanation: list[str]
    metrics: dict[str, Any]
    matrix_kind: str
    matrix_provider: str
    params: dict[str, Any]
    matrix: TravelMatrix | None = None
