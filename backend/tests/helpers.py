"""Small deterministic fixtures for optimizer tests."""

from datetime import date
from decimal import Decimal

from app.optimizer.domain import Candidate, DayPlan, Point, ProblemSpec, TravelMatrix
from app.optimizer.geo import haversine_m

KM = 0.009  # degrees of latitude per km (approx.)
MONDAY = date(2030, 1, 7)  # a Monday


def cand(key, km_north=0.0, km_east=0.0, minutes=60, **kw) -> Candidate:
    return Candidate(
        key=key,
        name=kw.pop("name", f"P{key}"),
        lat=40.0 + km_north * KM,
        lon=10.0 + km_east * KM,
        visit_minutes=minutes,
        **kw,
    )


def days(n=1, start=9 * 60, end=18 * 60):
    return [DayPlan(i, date.fromordinal(MONDAY.toordinal() + i), start, end) for i in range(n)]


def spec(cands, n_days=1, **kw) -> ProblemSpec:
    day_kw = {k: kw.pop(k) for k in ("start", "end") if k in kw}
    return ProblemSpec(candidates=cands, days=days(n_days, **day_kw), **kw)


def straight_matrix(points, mode="walking") -> TravelMatrix:
    keys = [p[0] for p in points]
    dist = [[haversine_m(a[1], a[2], b[1], b[2]) for b in points] for a in points]
    return TravelMatrix(keys, "straight_line_estimate", dist, None, "straight_line", mode)


def routed_matrix(points, mode="walking", speed_mps=1.2, detour=1.0, overrides=None) -> TravelMatrix:
    """Fabricated *test* routing data: duration = geometry * detour / speed."""
    keys = [p[0] for p in points]
    dist = [[haversine_m(a[1], a[2], b[1], b[2]) * detour for b in points] for a in points]
    dur = [[d / speed_mps for d in row] for row in dist]
    for (i, j), v in (overrides or {}).items():
        dur[keys.index(i)][keys.index(j)] = v
    return TravelMatrix(keys, "routed", dist, dur, "test", mode)


def straight_fn(points, mode):
    return straight_matrix(points, mode)


def routed_fn(**kw):
    return lambda points, mode: routed_matrix(points, mode, **kw)


def P(km_north=0.0, km_east=0.0, label=""):
    return Point(40.0 + km_north * KM, 10.0 + km_east * KM, label)


D = Decimal
