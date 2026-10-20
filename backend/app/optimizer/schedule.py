"""Schedule construction: turn ordered stops into timed days."""

from __future__ import annotations

from dataclasses import dataclass, field

from .domain import (
    Candidate,
    DayPlan,
    DaySchedule,
    ProblemSpec,
    ScheduledStop,
)
from .travel import TravelModel


def valid_start_ranges(c: Candidate, day: DayPlan) -> list[tuple[int, int]]:
    """Inclusive ranges of start times where the whole visit fits the day and hours."""
    v = c.visit_minutes
    if c.hours is None:
        lo, hi = day.start, day.end - v
        return [(lo, hi)] if lo <= hi else []
    out = []
    for o, cl in c.hours.get(day.weekday, []):
        lo, hi = max(o, day.start), min(cl, day.end) - v
        if lo <= hi:
            out.append((lo, hi))
    return out


def allowed_days(c: Candidate, days: list[DayPlan]) -> list[DayPlan]:
    """Days this candidate may use: respects pin/lock and opening hours."""
    fixed = c.locked_day if c.locked_day is not None else c.pinned_day
    return [d for d in days if (fixed is None or d.index == fixed) and valid_start_ranges(c, d)]


def earliest_start(c: Candidate, day: DayPlan, arrive: int) -> int | None:
    for lo, hi in valid_start_ranges(c, day):
        s = max(arrive, lo)
        if s <= hi:
            return s
    return None


@dataclass
class DaySim:
    day: DayPlan
    stops: list[ScheduledStop] = field(default_factory=list)
    violations: list[tuple[int | None, str, str]] = field(default_factory=list)
    visit_minutes: int = 0
    travel_minutes: int = 0
    wait_minutes: int = 0
    distance_m: float = 0.0
    work_minutes: int = 0
    end_time: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations


def pkey(k: int) -> str:
    return f"p{k}"


def simulate_day(
    spec: ProblemSpec,
    tm: TravelModel,
    day: DayPlan,
    seq: list[int],
    cmap: dict[int, Candidate],
) -> DaySim:
    sim = DaySim(day=day)
    t = day.start
    prev: str | None = "start" if spec.start_point else None
    for pos, k in enumerate(seq):
        c = cmap[k]
        key = pkey(k)
        travel = 0
        dist: float | None = None
        if prev is not None:
            travel = tm.minutes(prev, key)
            dist = tm.distance(prev, key)
            if not tm.reachable(prev, key):
                sim.violations.append((k, "unreachable", f"No route within your limits to '{c.name}'."))
                travel = 0
        arrive = t + travel
        start = earliest_start(c, day, arrive)
        warns: list[str] = []
        if start is None:
            ranges = valid_start_ranges(c, day)
            if not ranges:
                code, msg = "closed", f"'{c.name}' is closed or does not fit on this day."
            elif arrive + c.visit_minutes > day.end:
                code, msg = "day_end", f"'{c.name}' would end after the day ends."
            else:
                code, msg = "closed", f"'{c.name}' cannot be visited at the planned time."
            sim.violations.append((k, code, msg))
            warns.append(msg)
            start = arrive
        end = start + c.visit_minutes
        if start is not None and end > day.end and not any(v[0] == k for v in sim.violations):
            sim.violations.append((k, "day_end", f"'{c.name}' would end after the day ends."))
        wait = start - arrive
        sim.stops.append(
            ScheduledStop(
                key=k,
                day_index=day.index,
                position=pos,
                arrive=arrive,
                start=start,
                end=end,
                wait=wait,
                travel_minutes=travel if prev is not None else None,
                travel_basis=tm.basis if prev is not None else "none",
                distance_m=dist if prev is not None else None,
                distance_kind=tm.distance_kind if prev is not None else None,
                warnings=warns,
            )
        )
        sim.visit_minutes += c.visit_minutes
        sim.travel_minutes += travel
        sim.wait_minutes += wait
        sim.distance_m += dist or 0.0
        t = end
        prev = key
    if spec.end_point and prev is not None:
        back = tm.minutes(prev, "end")
        dist = tm.distance(prev, "end")
        if not tm.reachable(prev, "end"):
            sim.violations.append((None, "unreachable", "No route found to the end point."))
            back = 0
        sim.travel_minutes += back
        sim.distance_m += dist or 0.0
        t += back
        if t > day.end:
            sim.violations.append((seq[-1], "day_end", "Return to the end point is after the day ends."))
    sim.end_time = t
    sim.work_minutes = sim.visit_minutes + sim.travel_minutes
    if spec.max_daily_minutes is not None and sim.work_minutes > spec.max_daily_minutes:
        sim.violations.append(
            (
                seq[-1] if seq else None,
                "workload",
                f"Day workload {sim.work_minutes} min exceeds the {spec.max_daily_minutes} min limit.",
            )
        )
    if tm.routed and spec.max_travel_minutes is not None and sim.travel_minutes > spec.max_travel_minutes:
        sim.violations.append(
            (
                seq[-1] if seq else None,
                "max_travel",
                f"Travel {sim.travel_minutes} min exceeds the {spec.max_travel_minutes} min limit.",
            )
        )
    return sim


def day_cost(spec: ProblemSpec, tm: TravelModel, seq: list[int]) -> int:
    if not seq:
        return 0
    total = 0
    prev = "start" if spec.start_point else None
    for k in seq:
        key = pkey(k)
        if prev is not None:
            total += tm.cost(prev, key)
        prev = key
    if spec.end_point and prev is not None:
        total += tm.cost(prev, "end")
    return total


def to_day_schedule(sim: DaySim, tm: TravelModel) -> DaySchedule:
    return DaySchedule(
        day_index=sim.day.index,
        date=sim.day.date,
        stops=sim.stops,
        visit_minutes=sim.visit_minutes,
        travel_minutes=sim.travel_minutes,
        wait_minutes=sim.wait_minutes,
        distance_m=round(sim.distance_m, 1),
        distance_kind=tm.distance_kind,
        day_end_used=sim.end_time,
    )
