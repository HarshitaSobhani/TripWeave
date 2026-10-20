"""Stage 3 (constraint validation) and stage 6 (result validation)."""

from __future__ import annotations

from typing import Literal

from .domain import (
    Candidate,
    DaySchedule,
    Issue,
    ProblemSpec,
    Unscheduled,
)
from .schedule import allowed_days
from .selection import day_capacity, is_forced


def validate_spec(spec: ProblemSpec) -> list[Issue]:
    issues: list[Issue] = []
    if not spec.days:
        issues.append(Issue("error", "no_days", "The trip has no days to plan."))
        return issues
    for d in spec.days:
        if d.start >= d.end:
            issues.append(Issue("error", "bad_window", "Day start must be before day end.", day_index=d.index))
    if spec.travelers < 1:
        issues.append(Issue("error", "travelers", "At least one traveller is required."))
    if spec.max_daily_minutes is not None and spec.max_daily_minutes <= 0:
        issues.append(Issue("error", "bad_workload", "Maximum daily workload must be positive."))
    if spec.max_travel_minutes is not None:
        issues.append(
            Issue(
                "info", "max_travel_note", "Maximum daily travel is enforced only when real routing data is available."
            )
        )
    ids = {d.index for d in spec.days}
    unknown_hours = 0
    forced_minutes = 0
    for c in spec.candidates:
        if not (-90 <= c.lat <= 90 and -180 <= c.lon <= 180):
            issues.append(Issue("error", "bad_coords", f"'{c.name}' has invalid coordinates.", c.key))
        if c.visit_minutes <= 0:
            issues.append(Issue("error", "bad_duration", f"'{c.name}' needs a positive visit duration.", c.key))
        if not 1 <= c.interest <= 5:
            issues.append(Issue("error", "bad_interest", f"'{c.name}' interest must be 1-5.", c.key))
        if c.hours is None:
            unknown_hours += 1
        for label, day in (("pinned", c.pinned_day), ("locked", c.locked_day)):
            if day is not None and day not in ids:
                issues.append(Issue("error", "bad_day", f"'{c.name}' is {label} to a day outside the trip.", c.key))
        if c.pinned_day is not None and c.locked_day is not None and c.pinned_day != c.locked_day:
            issues.append(
                Issue(
                    "warning",
                    "pin_conflict",
                    f"'{c.name}' is pinned to day {c.pinned_day + 1} but manually placed on day {c.locked_day + 1}; the manual placement wins.",
                    c.key,
                )
            )
        feasible_days = allowed_days(c, spec.days)
        if is_forced(c):
            forced_minutes += c.visit_minutes
        if not feasible_days:
            sev: Literal["error", "warning"] = "error" if is_forced(c) or c.pinned_day is not None else "warning"
            issues.append(
                Issue(
                    sev,
                    "no_feasible_day",
                    f"'{c.name}' cannot fit on any allowed day (opening hours, day window or visit length).",
                    c.key,
                )
            )
    if unknown_hours:
        issues.append(
            Issue(
                "info",
                "hours_unknown",
                f"{unknown_hours} place(s) have no verified opening hours; they are assumed open and should be checked.",
            )
        )
    if forced_minutes > day_capacity(spec):
        issues.append(
            Issue(
                "error",
                "mandatory_exceeds_capacity",
                "Mandatory and locked visit time alone exceeds the available daily time.",
            )
        )
    return issues


def validate_result(
    spec: ProblemSpec,
    days: list[DaySchedule],
    unscheduled: list[Unscheduled],
    cmap: dict[int, Candidate],
) -> list[Issue]:
    """Independent re-check of a finished schedule."""
    issues: list[Issue] = []
    seen: set[int] = set()
    placed: set[int] = set()
    dmap = {d.index: d for d in spec.days}
    for ds in days:
        day = dmap[ds.day_index]
        last_end = day.start
        for s in ds.stops:
            c = cmap[s.key]
            placed.add(s.key)
            if s.key in seen:
                issues.append(
                    Issue("error", "validation_duplicate", f"'{c.name}' appears more than once.", s.key, ds.day_index)
                )
            seen.add(s.key)
            if s.start < last_end:
                issues.append(
                    Issue("error", "validation_overlap", f"'{c.name}' overlaps the previous stop.", s.key, ds.day_index)
                )
            if s.end - s.start != c.visit_minutes:
                issues.append(
                    Issue("error", "validation_duration", f"'{c.name}' duration mismatch.", s.key, ds.day_index)
                )
            if s.start < day.start or s.end > day.end:
                issues.append(
                    Issue(
                        "warning",
                        "validation_day_window",
                        f"'{c.name}' falls outside the daily time window.",
                        s.key,
                        ds.day_index,
                    )
                )
            if c.hours is not None:
                wins = c.hours.get(day.weekday, [])
                if not any(o <= s.start and s.end <= cl for o, cl in wins):
                    issues.append(
                        Issue(
                            "warning",
                            "validation_hours",
                            f"'{c.name}' is scheduled outside its opening hours.",
                            s.key,
                            ds.day_index,
                        )
                    )
            last_end = s.end
        work = ds.visit_minutes + ds.travel_minutes
        if spec.max_daily_minutes is not None and work > spec.max_daily_minutes:
            issues.append(
                Issue(
                    "warning",
                    "validation_workload",
                    f"Day {ds.day_index + 1} workload {work} min exceeds limit.",
                    None,
                    ds.day_index,
                )
            )
    un = {u.key for u in unscheduled}
    for c in spec.candidates:
        if c.mandatory and c.key not in placed and c.key not in un:
            issues.append(
                Issue(
                    "error",
                    "validation_mandatory_missing",
                    f"Mandatory stop '{c.name}' was neither scheduled nor reported.",
                    c.key,
                )
            )
    both = placed & un
    for k in both:
        issues.append(Issue("error", "validation_both", f"'{cmap[k].name}' is both scheduled and unscheduled.", k))
    return issues


__all__ = ["validate_result", "validate_spec"]
