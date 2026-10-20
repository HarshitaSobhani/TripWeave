"""Orchestrates the seven stages:

1 selection -> 2 matrix acquisition -> 3 constraint validation -> 4 optimization
-> 5 schedule construction -> 6 result validation -> 7 explanation/warnings.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .domain import (
    Candidate,
    DaySchedule,
    Issue,
    OptimizationResult,
    ProblemSpec,
    TravelMatrix,
    Unscheduled,
)
from .schedule import DaySim, allowed_days, pkey, simulate_day, to_day_schedule
from .selection import is_forced, select_places
from .solvers import (
    SolverUnavailable,
    default_balance_weight,
    default_interest_weight,
    solve_fallback,
    solve_ortools,
)
from .travel import TravelModel
from .validation import validate_result, validate_spec

# (key, lat, lon) points -> matrix. Called once, after place selection.
MatrixFn = Callable[[list[tuple[str, float, float]], str], TravelMatrix]
OVERLOAD_CODES = {"day_end", "workload", "max_travel"}


def _points(spec: ProblemSpec, keys: list[int]) -> list[tuple[str, float, float]]:
    pts: list[tuple[str, float, float]] = []
    if spec.start_point:
        pts.append(("start", spec.start_point.lat, spec.start_point.lon))
    if spec.end_point:
        pts.append(("end", spec.end_point.lat, spec.end_point.lon))
    cmap = {c.key: c for c in spec.candidates}
    for k in sorted(set(keys)):
        pts.append((pkey(k), cmap[k].lat, cmap[k].lon))
    return pts


def _finalize_day(
    spec: ProblemSpec, tm: TravelModel, day, seq: list[int], cmap: dict[int, Candidate]
) -> tuple[DaySim, list[Unscheduled]]:
    seq = list(seq)
    dropped: list[Unscheduled] = []
    while True:
        sim = simulate_day(spec, tm, day, seq, cmap)
        if sim.ok:
            return sim, dropped
        victims = [(k, code, msg) for k, code, msg in sim.violations if k is not None and not is_forced(cmap[k])]
        if victims:
            k, code, msg = victims[-1]
        elif any(code in OVERLOAD_CODES for _, code, _ in sim.violations):
            movable = [k for k in seq if not is_forced(cmap[k])]
            if not movable:
                return sim, dropped
            k = min(movable, key=lambda x: (cmap[x].interest, -seq.index(x)))
            code, msg = "no_time", "Removed to keep the day within its limits."
        else:
            return sim, dropped
        seq.remove(k)
        dropped.append(Unscheduled(k, code if code != "day_end" else "no_time", msg))


def _apply_locks(spec: ProblemSpec, seqs: dict[int, list[int]], cmap: dict[int, Candidate]) -> None:
    """Keep locked stops on their day; restore their relative manual order."""
    placed = {k for s in seqs.values() for k in s}
    for c in sorted(cmap.values(), key=lambda c: c.key):
        if c.locked_day is not None and c.key not in placed and c.locked_day in seqs:
            seqs[c.locked_day].append(c.key)
    for di, seq in seqs.items():
        locked = [k for k in seq if cmap[k].locked_day == di]
        wanted = sorted(locked, key=lambda k: (cmap[k].locked_order if cmap[k].locked_order is not None else 10**6, k))
        slots = [i for i, k in enumerate(seq) if k in set(locked)]
        for slot, k in zip(slots, wanted, strict=True):
            seq[slot] = k


def _metrics(spec: ProblemSpec, tm: TravelModel, days: list[DaySchedule], cmap: dict[int, Candidate]) -> dict[str, Any]:
    n = sum(len(d.stops) for d in days)
    interest = sum(cmap[s.key].interest for d in days for s in d.stops)
    visit = sum(d.visit_minutes for d in days)
    dist = sum(d.distance_m for d in days)
    return {
        "stops": n,
        "interest_total": interest,
        "visit_minutes": visit,
        "travel_minutes": sum(d.travel_minutes for d in days) if tm.routed else None,
        "buffer_minutes": None if tm.routed else sum(d.travel_minutes for d in days),
        "wait_minutes": sum(d.wait_minutes for d in days),
        "distance_m": round(dist, 1),
        "distance_kind": tm.distance_kind,
        "distance_note": (
            "Routed distance from the routing provider."
            if tm.routed
            else "Straight-line (great-circle) estimate. Not a route and not a travel time."
        ),
    }


def evaluate(
    spec: ProblemSpec, tm: TravelModel, seqs: dict[int, list[int]]
) -> tuple[list[DaySchedule], list[DaySim], dict[str, Any]]:
    cmap = {c.key: c for c in spec.candidates}
    sims = [simulate_day(spec, tm, d, seqs.get(d.index, []), cmap) for d in spec.days]
    days = [to_day_schedule(s, tm) for s in sims]
    return days, sims, _metrics(spec, tm, days, cmap)


def schedule_only(spec: ProblemSpec, get_matrix: MatrixFn, seqs: dict[int, list[int]]) -> OptimizationResult:
    """Time an existing (e.g. manually edited) order without reordering anything."""
    cmap = {c.key: c for c in spec.candidates}
    keys = [k for s in seqs.values() for k in s]
    matrix = get_matrix(_points(spec, keys), spec.mode)
    tm = TravelModel(matrix, spec.transit_buffer_minutes, spec.max_leg_minutes)
    days, sims, metrics = evaluate(spec, tm, seqs)
    issues = [Issue("info", "matrix_note", n) for n in matrix.notes]
    for sim in sims:
        for k, code, msg in sim.violations:
            issues.append(Issue("warning", f"schedule_{code}", msg, k, sim.day.index))
    dup = [k for k in keys if keys.count(k) > 1]
    for k in sorted(set(dup)):
        issues.append(Issue("error", "validation_duplicate", f"'{cmap[k].name}' appears more than once.", k))
    status = (
        "feasible" if not any(i.severity == "error" or i.code.startswith("schedule_") for i in issues) else "infeasible"
    )
    return OptimizationResult(
        status=status,  # type: ignore[arg-type]
        solver="manual",
        days=days,
        unscheduled=[],
        issues=issues,
        explanation=["Times recomputed for the current manual order; nothing was reordered."],
        metrics=metrics,
        matrix_kind=matrix.kind,
        matrix_provider=matrix.provider,
        params={"mode": spec.mode, "buffer": spec.transit_buffer_minutes},
        matrix=matrix,
    )


def optimize(
    spec: ProblemSpec,
    get_matrix: MatrixFn,
    solver: str = "auto",
    baseline: dict[int, list[int]] | None = None,
) -> OptimizationResult:
    issues = validate_spec(spec)
    if not spec.days:
        return OptimizationResult("infeasible", "none", [], [], issues, [], {}, "none", "none", {})

    sel = select_places(spec)
    issues += sel.issues
    unscheduled: list[Unscheduled] = list(sel.deferred)
    cmap = {c.key: c for c in spec.candidates}

    # forced stops with no usable day are infeasible: report, don't send to solver
    solvable: list[Candidate] = []
    for c in sel.selected:
        if allowed_days(c, spec.days):
            solvable.append(c)
        else:
            unscheduled.append(
                Unscheduled(
                    c.key,
                    "infeasible" if is_forced(c) else "closed",
                    "No allowed day where this place is open and the visit fits.",
                )
            )

    if not solvable:
        empty = [DaySchedule(d.index, d.date, [], 0, 0, 0, 0.0, "none", d.start) for d in spec.days]
        return OptimizationResult(
            "infeasible" if any(i.severity == "error" for i in issues) else "empty",
            "none",
            empty,
            unscheduled,
            issues,
            ["No stops could be scheduled."],
            {},
            "none",
            "none",
            {},
        )

    base_keys = [k for s in (baseline or {}).values() for k in s]
    matrix = get_matrix(_points(spec, [c.key for c in solvable] + base_keys), spec.mode)
    issues += [Issue("info", "matrix_note", n) for n in matrix.notes]
    tm = TravelModel(matrix, spec.transit_buffer_minutes, spec.max_leg_minutes)
    if spec.max_leg_minutes is not None and not tm.routed:
        issues.append(
            Issue(
                "warning",
                "max_leg_not_enforced",
                "The maximum single-leg travel limit needs real routing data and was not enforced.",
            )
        )
    if not tm.routed:
        issues.append(
            Issue(
                "warning",
                "no_routing",
                "No real routing data: stops are ordered by straight-line distance (an estimate, not a route) and "
                f"scheduled with your {spec.transit_buffer_minutes}-minute transit buffer. Travel times are unknown.",
            )
        )

    used = solver
    seqs: dict[int, list[int]]
    if solver in ("auto", "ortools"):
        try:
            seqs = solve_ortools(spec, solvable, tm)
            used = "ortools"
        except SolverUnavailable as exc:
            if solver == "ortools":
                raise
            issues.append(Issue("warning", "solver_fallback", f"{exc}; used the heuristic fallback optimizer."))
            seqs = solve_fallback(spec, solvable, tm)
            used = "fallback"
    elif solver == "fallback":
        seqs = solve_fallback(spec, solvable, tm)
    else:
        raise ValueError(f"unknown solver '{solver}'")

    _apply_locks(spec, seqs, {c.key: c for c in solvable})

    days: list[DaySchedule] = []
    placed: set[int] = set()
    for d in spec.days:
        sim, dropped = _finalize_day(spec, tm, d, seqs.get(d.index, []), cmap)
        unscheduled += dropped
        for k, code, msg in sim.violations:
            issues.append(Issue("warning", f"locked_{code}", msg, k, d.index))
        days.append(to_day_schedule(sim, tm))
        placed.update(s.key for s in sim.stops)

    known = {u.key for u in unscheduled}
    for c in solvable:
        if c.key not in placed and c.key not in known:
            unscheduled.append(
                Unscheduled(
                    c.key,
                    "infeasible" if is_forced(c) else "no_time",
                    "Could not be placed within daily limits."
                    if is_forced(c)
                    else "Lower value than the stops chosen within time/workload limits.",
                )
            )

    unscheduled = sorted({u.key: u for u in unscheduled}.values(), key=lambda u: u.key)
    issues += validate_result(spec, days, unscheduled, cmap)
    for u in unscheduled:
        c = cmap[u.key]
        if c.mandatory:
            issues.append(
                Issue(
                    "error",
                    "mandatory_unscheduled",
                    f"Mandatory stop '{c.name}' could not be scheduled: {u.detail}",
                    c.key,
                )
            )
        elif c.locked_day is not None:
            issues.append(
                Issue("error", "locked_unscheduled", f"Manual stop '{c.name}' could not be kept: {u.detail}", c.key)
            )

    metrics = _metrics(spec, tm, days, cmap)
    metrics["spend"] = str(sel.spend)
    if baseline and any(baseline.values()):
        _, _, before = evaluate(spec, tm, baseline)
        metrics["before"] = before
    status = "infeasible" if any(i.severity == "error" for i in issues) else "feasible"
    if not any(d.stops for d in days):
        status = "infeasible" if status == "infeasible" else "empty"
    iw = spec.interest_weight if spec.interest_weight is not None else default_interest_weight(tm)
    bw = spec.balance_weight if spec.balance_weight is not None else default_balance_weight(tm)
    params = {
        "solver": used,
        "mode": spec.mode,
        "buffer_minutes": spec.transit_buffer_minutes,
        "interest_weight": iw,
        "balance_weight": bw,
        "max_daily_minutes": spec.max_daily_minutes,
        "max_travel_minutes": spec.max_travel_minutes,
        "matrix_kind": matrix.kind,
        "matrix_provider": matrix.provider,
    }
    from .explain import explain  # local import avoids a cycle

    result = OptimizationResult(
        status=status,  # type: ignore[arg-type]
        solver=used,
        days=days,
        unscheduled=unscheduled,
        issues=issues,
        explanation=[],
        metrics=metrics,
        matrix_kind=matrix.kind,
        matrix_provider=matrix.provider,
        params=params,
        matrix=matrix,
    )
    result.explanation = explain(spec, tm, result, cmap)
    return result
