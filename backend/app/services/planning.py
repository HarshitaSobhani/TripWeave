"""DB <-> optimizer glue: build problems, run them, persist schedules, edit stops."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import Settings
from ..optimizer import optimize
from ..optimizer.domain import Candidate, DayPlan, Issue, OptimizationResult, Point, ProblemSpec
from ..optimizer.hours import parse_hours
from ..optimizer.pipeline import schedule_only
from ..optimizer.serialize import matrix_from_json, matrix_to_json, result_to_json, spec_from_json, spec_to_json
from ..routing import acquire_matrix

DEFAULT_VISIT_MINUTES = 60  # planner default when neither place nor user gives a duration


class ManualEditsConflict(Exception):
    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__("manual edits would be replaced")


def _mins(t) -> int:
    return t.hour * 60 + t.minute


def ensure_days(db: Session, trip: m.Trip) -> None:
    """Make sure one TripDay row exists per calendar day in range; drop days outside."""
    from datetime import timedelta

    want = [trip.start_date + timedelta(days=i) for i in range((trip.end_date - trip.start_date).days + 1)]
    existing = {d.day_index: d for d in trip.days}
    for i, dt in enumerate(want):
        if i in existing:
            existing[i].date = dt
        else:
            trip.days.append(m.TripDay(day_index=i, date=dt))
    doomed = [d for idx, d in existing.items() if idx >= len(want)]
    busy = [d.day_index + 1 for d in doomed if d.stops]
    if busy:
        raise ValueError(
            f"Shortening the trip would delete stops on day(s) {', '.join(map(str, busy))}. "
            "Move or remove those stops first."
        )
    for d in doomed:
        trip.days.remove(d)
    db.flush()


def build_spec(
    db: Session,
    trip: m.Trip,
    replace_manual: bool = False,
    interest_weight: float | None = None,
    balance_weight: float | None = None,
) -> tuple[ProblemSpec, list[Issue]]:
    issues: list[Issue] = []
    stop_by_place = {s.place_id: s for d in trip.days for s in d.stops}
    day_index_of = {s.place_id: d.day_index for d in trip.days for s in d.stops}
    pins = {c.value["place_id"]: c.value["day_index"] for c in trip.constraints if c.kind == "pin_day"}
    cands: list[Candidate] = []
    defaulted: list[str] = []
    for tp in sorted(trip.candidates, key=lambda t: t.place_id):
        if tp.status == "excluded":
            continue
        p = tp.place
        raw_hours = tp.hours_override if tp.hours_override is not None else p.opening_hours
        try:
            hours = parse_hours(raw_hours)
        except ValueError:
            hours = None
            issues.append(
                Issue("warning", "bad_hours", f"Opening hours for '{p.name}' are invalid and were ignored.", p.id)
            )
        minutes = tp.visit_minutes or p.visit_minutes
        if minutes is None:
            minutes = DEFAULT_VISIT_MINUTES
            defaulted.append(p.name)
        stop = stop_by_place.get(p.id)
        locked = bool(stop and stop.locked and not replace_manual)
        cands.append(
            Candidate(
                key=p.id,
                name=p.name,
                lat=p.lat,
                lon=p.lon,
                visit_minutes=minutes,
                interest=tp.interest,
                mandatory=tp.status == "mandatory",
                cost=p.cost,
                cost_currency=p.cost_currency,
                hours=hours,
                pinned_day=pins.get(p.id),
                locked_day=day_index_of[p.id] if locked else None,
                locked_order=stop.position if locked and stop else None,
                category=p.category,
            )
        )
    if defaulted:
        shown = ", ".join(defaulted[:4]) + (f" and {len(defaulted) - 4} more" if len(defaulted) > 4 else "")
        issues.append(
            Issue(
                "info",
                "default_duration",
                f"{len(defaulted)} place(s) have no visit duration (e.g. {shown}); the planner default of "
                f"{DEFAULT_VISIT_MINUTES} min is used. Set real durations in the Places tab.",
            )
        )
    days = [DayPlan(d.day_index, d.date, _mins(trip.day_start), _mins(trip.day_end)) for d in trip.days]
    committed = sum((e.amount for e in trip.expenses if e.currency == trip.currency), Decimal("0"))

    def pt(v: dict | None) -> Point | None:
        return Point(v["lat"], v["lon"], v.get("label", "")) if v else None

    spec = ProblemSpec(
        candidates=cands,
        days=days,
        travelers=trip.travelers,
        budget=trip.budget,
        currency=trip.currency,
        committed_spend=committed,
        max_daily_minutes=trip.max_daily_minutes,
        max_travel_minutes=trip.max_travel_minutes,
        max_leg_minutes=trip.max_walk_minutes,
        transit_buffer_minutes=trip.transit_buffer_minutes,
        start_point=pt(trip.start_point),
        end_point=pt(trip.end_point),
        interest_weight=interest_weight,
        balance_weight=balance_weight,
        mode=trip.travel_mode,
    )
    acc = trip.accessibility or {}
    if acc.get("step_free") or acc.get("notes"):
        issues.append(
            Issue(
                "warning",
                "accessibility_unverified",
                "Accessibility needs are recorded, but the place catalog has no verified accessibility data. Check each stop before relying on this plan.",
            )
        )
    other = {e.currency for e in trip.expenses if e.currency != trip.currency}
    if other:
        issues.append(
            Issue(
                "info",
                "expense_currencies",
                f"Expenses in {', '.join(sorted(other))} are not counted against the {trip.currency} budget (no conversion).",
            )
        )
    return spec, issues


def _baseline(trip: m.Trip, spec: ProblemSpec) -> dict[int, list[int]]:
    keys = {c.key for c in spec.candidates}
    return {
        d.day_index: [s.place_id for s in sorted(d.stops, key=lambda x: x.position) if s.place_id in keys]
        for d in trip.days
    }


def _hash(spec_json: dict, matrix_json: dict, solver: str) -> str:
    core = {
        "spec": spec_json,
        "solver": solver,
        "matrix": {k: matrix_json[k] for k in ("keys", "kind", "distances_m", "durations_s", "provider", "mode")},
    }
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def payload(res: OptimizationResult, spec: ProblemSpec, extra_issues: list[Issue]) -> dict[str, Any]:
    out = result_to_json(res)
    names = {c.key: c.name for c in spec.candidates}
    for u in out["unscheduled"]:
        u["name"] = names.get(u["key"], str(u["key"]))
    out["issues"] = [i.as_dict() for i in extra_issues] + out["issues"]
    return out


def _persist_schedule(db: Session, trip: m.Trip, res: OptimizationResult, spec: ProblemSpec) -> None:
    days = {d.day_index: d for d in trip.days}
    existing = {s.place_id: s for d in trip.days for s in d.stops}
    cmap = {c.key: c for c in spec.candidates}
    keep: set[int] = set()
    for ds in res.days:
        day = days[ds.day_index]
        for s in ds.stops:
            stop = existing.get(s.key)
            c = cmap[s.key]
            if stop is None:
                stop = m.Stop(
                    trip_id=trip.id, place_id=s.key, origin="optimized", locked=False, visit_minutes=c.visit_minutes
                )
                db.add(stop)
            stop.day = day
            stop.trip_day_id = day.id
            stop.position = s.position
            stop.visit_minutes = c.visit_minutes
            stop.arrive_min, stop.start_min, stop.end_min, stop.wait_min = s.arrive, s.start, s.end, s.wait
            stop.leg_minutes, stop.leg_basis = s.travel_minutes, s.travel_basis
            stop.leg_distance_m, stop.leg_distance_kind = s.distance_m, s.distance_kind
            stop.warnings = s.warnings or None
            if not stop.locked:
                stop.origin = "optimized"
            keep.add(s.key)
    # manual stops that could not be scheduled are kept, never silently discarded
    for pid, stop in existing.items():
        if pid in keep:
            continue
        reason = next((u.detail for u in res.unscheduled if u.key == pid), "not scheduled")
        if stop.locked and res.solver != "manual":
            stop.warnings = [f"Could not be scheduled: {reason}"]
            stop.arrive_min = stop.start_min = stop.end_min = stop.wait_min = None
            stop.leg_minutes = stop.leg_distance_m = None
            keep.add(pid)
        else:
            db.delete(stop)
    db.flush()
    db.expire(trip, ["days"])


def _store_legs(db: Session, run: m.OptimizationRun, res: OptimizationResult, spec: ProblemSpec) -> None:
    if res.matrix is None:
        return
    mx = res.matrix
    now = datetime.now(UTC)
    for ds in res.days:
        prev = "start" if spec.start_point else None
        for s in ds.stops:
            cur = f"p{s.key}"
            if prev is not None and prev in mx._idx and cur in mx._idx:
                i, j = mx.idx(prev), mx.idx(cur)
                run.legs.append(
                    m.RouteLeg(
                        day_index=ds.day_index,
                        from_place_id=int(prev[1:]) if prev.startswith("p") else None,
                        to_place_id=s.key,
                        kind=mx.kind,
                        provider=mx.provider,
                        mode=mx.mode,
                        duration_s=mx.durations_s[i][j] if mx.durations_s else None,
                        distance_m=mx.distances_m[i][j],
                        fetched_at=now,
                    )
                )
            prev = cur


def run_optimization(
    db: Session,
    trip: m.Trip,
    settings: Settings,
    solver: str = "auto",
    replace_manual: bool = False,
    confirm_replace_manual: bool = False,
    interest_weight: float | None = None,
    balance_weight: float | None = None,
    preview: bool = False,
    matrix_fn=None,
) -> tuple[dict[str, Any], m.OptimizationRun | None]:
    locked = [s for d in trip.days for s in d.stops if s.locked]
    if replace_manual and locked and not confirm_replace_manual:
        raise ManualEditsConflict([s.place.name for s in locked])
    spec, extra = build_spec(db, trip, replace_manual, interest_weight, balance_weight)
    fn = matrix_fn or (lambda pts, mode: acquire_matrix(settings, pts, mode))
    res = optimize(spec, fn, solver, baseline=_baseline(trip, spec))
    out = payload(res, spec, extra)
    if preview:
        return out, None
    if replace_manual:
        for s in locked:
            s.locked = False
            s.origin = "optimized"
    _persist_schedule(db, trip, res, spec)
    spec_json = spec_to_json(spec)
    mj = (
        matrix_to_json(res.matrix)
        if res.matrix
        else {"keys": [], "kind": "none", "distances_m": [], "durations_s": None, "provider": "none", "mode": spec.mode}
    )
    run = m.OptimizationRun(
        trip_id=trip.id,
        kind="optimize",
        status=res.status,
        solver=res.solver,
        matrix_kind=res.matrix_kind,
        matrix_provider=res.matrix_provider,
        input_hash=_hash(spec_json, mj, solver),
        params={**res.params, "requested_solver": solver},
        input_snapshot={"spec": spec_json, "matrix": mj},
        result=out,
    )
    db.add(run)
    db.flush()
    _store_legs(db, run, res, spec)
    db.commit()
    db.refresh(trip)
    return out, run


def reproduce(run: m.OptimizationRun) -> dict[str, Any]:
    """Re-run a stored optimization from its snapshot (no network, no DB data)."""
    spec = spec_from_json(run.input_snapshot["spec"])
    matrix = matrix_from_json(run.input_snapshot["matrix"])
    res = optimize(spec, lambda pts, mode: matrix, run.params.get("requested_solver", "auto"))
    return payload(res, spec, [])


def retime(db: Session, trip: m.Trip, settings: Settings, matrix_fn=None) -> dict[str, Any]:
    """Recompute times for the current order (after manual edits). Never reorders."""
    spec, extra = build_spec(db, trip)
    seqs = {d.day_index: [s.place_id for s in sorted(d.stops, key=lambda x: x.position)] for d in trip.days}
    fn = matrix_fn or (lambda pts, mode: acquire_matrix(settings, pts, mode))
    res = schedule_only(spec, fn, seqs)
    out = payload(res, spec, extra)
    _persist_schedule(db, trip, res, spec)
    last = trip.runs[-1] if trip.runs else None
    mj = matrix_to_json(res.matrix) if res.matrix else {}
    spec_json = spec_to_json(spec)
    if last is not None and last.kind == "reschedule":
        run = last
        run.status, run.result = res.status, out
        run.input_snapshot = {"spec": spec_json, "matrix": mj}
        run.matrix_kind, run.matrix_provider = res.matrix_kind, res.matrix_provider
        run.created_at = datetime.now(UTC)
    else:
        run = m.OptimizationRun(
            trip_id=trip.id,
            kind="reschedule",
            status=res.status,
            solver="manual",
            matrix_kind=res.matrix_kind,
            matrix_provider=res.matrix_provider,
            input_hash=_hash(spec_json, mj, "manual") if mj else "",
            params=res.params,
            input_snapshot={"spec": spec_json, "matrix": mj},
            result=out,
        )
        db.add(run)
    db.commit()
    db.refresh(trip)
    return out


# ---- stop editing
def _day(trip: m.Trip, idx: int) -> m.TripDay:
    for d in trip.days:
        if d.day_index == idx:
            return d
    raise ValueError(f"day {idx} is outside the trip")


def _reindex(day: m.TripDay) -> None:
    for i, s in enumerate(sorted(day.stops, key=lambda s: s.position)):
        s.position = i


def ensure_candidate(db: Session, trip: m.Trip, place: m.Place) -> m.TripPlace:
    for tp in trip.candidates:
        if tp.place_id == place.id:
            if tp.status == "excluded":
                tp.status = "optional"
            return tp
    interests = {i.lower() for i in (trip.interests or [])}
    tp = m.TripPlace(trip_id=trip.id, place_id=place.id, interest=4 if place.category.lower() in interests else 3)
    tp.place = place
    trip.candidates.append(tp)
    db.flush()
    return tp


def add_stop(
    db: Session,
    trip: m.Trip,
    place: m.Place,
    day_index: int,
    position: int | None,
    minutes: int | None,
    notes: str | None,
) -> m.Stop:
    if any(s.place_id == place.id for d in trip.days for s in d.stops):
        raise ValueError("this place is already in the itinerary")
    day = _day(trip, day_index)
    tp = ensure_candidate(db, trip, place)
    if minutes:
        tp.visit_minutes = minutes
    stop = m.Stop(
        trip_id=trip.id,
        place_id=place.id,
        visit_minutes=minutes or tp.visit_minutes or place.visit_minutes or DEFAULT_VISIT_MINUTES,
        notes=notes,
        origin="manual",
        locked=True,
        position=0,
    )
    stop.place = place
    pos = len(day.stops) if position is None else min(position, len(day.stops))
    for s in day.stops:
        if s.position >= pos:
            s.position += 1
    stop.position = pos
    day.stops.append(stop)
    db.flush()
    _reindex(day)
    return stop


def move_stop(db: Session, trip: m.Trip, stop: m.Stop, day_index: int | None, position: int | None) -> None:
    src = stop.day
    dst = _day(trip, day_index) if day_index is not None else src
    if dst is not src:
        src.stops.remove(stop)
        dst.stops.append(stop)
        stop.trip_day_id = dst.id
        _reindex(src)
    others = sorted((s for s in dst.stops if s is not stop), key=lambda s: s.position)
    pos = len(others) if position is None else min(position, len(others))
    others.insert(pos, stop)
    for i, s in enumerate(others):
        s.position = i
    stop.origin = "manual"
    stop.locked = True
    db.flush()


def remove_stop(db: Session, trip: m.Trip, stop: m.Stop, forget: bool) -> None:
    day = stop.day
    pid = stop.place_id
    day.stops.remove(stop)
    db.delete(stop)
    db.flush()
    _reindex(day)
    for tp in list(trip.candidates):
        if tp.place_id == pid:
            if forget:
                trip.candidates.remove(tp)
            else:
                tp.status = "excluded"


def visible_place_filter(user_id: int):
    return (m.Place.owner_id.is_(None)) | (m.Place.owner_id == user_id)


def get_place_for_user(db: Session, user_id: int, place_id: int) -> m.Place | None:
    return db.scalar(select(m.Place).where(m.Place.id == place_id, visible_place_filter(user_id)))
