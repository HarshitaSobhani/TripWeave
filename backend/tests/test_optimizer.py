import pytest

from app.optimizer import optimize
from app.optimizer.domain import TravelMatrix
from app.optimizer.hours import parse_hours
from app.optimizer.pipeline import schedule_only
from app.optimizer.selection import dedupe, select_places
from app.optimizer.validation import validate_spec

from .helpers import D, P, cand, routed_fn, spec, straight_fn

SOLVERS = ["ortools", "fallback"]


def order(res, day=0):
    return [s.key for s in res.days[day].stops]


@pytest.mark.parametrize("solver", SOLVERS)
def test_route_ordering_on_a_line(solver):
    # P1..P4 are 1 km apart along a line; shuffled input; start at the P1 end.
    cs = [cand(3, 2), cand(1, 0), cand(4, 3), cand(2, 1)]
    s = spec(cs, start_point=P(-0.1))
    res = optimize(s, routed_fn(), solver)
    assert order(res) == [1, 2, 3, 4]
    assert res.status == "feasible"
    assert res.matrix_kind == "routed"


@pytest.mark.parametrize("solver", SOLVERS)
def test_ordering_with_start_and_end_returns_efficiently(solver):
    cs = [cand(1, 1), cand(2, 3), cand(3, 2)]
    s = spec(cs, start_point=P(0), end_point=P(0))
    res = optimize(s, routed_fn(), solver)
    assert res.metrics["distance_m"] == pytest.approx(6000, rel=0.02)


@pytest.mark.parametrize("solver", SOLVERS)
def test_daily_window_drops_lowest_interest(solver):
    cs = [
        cand(1, 0, interest=5, minutes=90),
        cand(2, 0.1, interest=4, minutes=90),
        cand(3, 0.2, interest=1, minutes=90),
    ]
    s = spec(cs, start=9 * 60, end=12 * 60 + 30, transit_buffer_minutes=5)
    res = optimize(s, straight_fn, solver)
    assert sorted(order(res)) == [1, 2]
    assert [u.key for u in res.unscheduled] == [3]
    for st in res.days[0].stops:
        assert st.end <= 12 * 60 + 30


@pytest.mark.parametrize("solver", SOLVERS)
def test_mandatory_kept_over_higher_interest(solver):
    cs = [cand(1, 0, interest=5, minutes=120), cand(2, 0.1, interest=1, minutes=120, mandatory=True)]
    s = spec(cs, start=9 * 60, end=12 * 60)
    res = optimize(s, straight_fn, solver)
    assert order(res) == [2]
    assert res.status == "feasible"


def test_duplicate_elimination():
    a = cand(1, 0, name="Museum")
    b = cand(2, 0, name="museum")  # same name and place
    c = cand(1, 0, name="Museum")  # same key
    kept, dropped = dedupe([a, b, c, cand(3, 5)])
    assert sorted(x.key for x in kept) == [1, 3]
    assert {u.code for u in dropped} == {"duplicate"}
    res = optimize(spec([a, b, c, cand(3, 5)]), straight_fn)
    keys = order(res)
    assert len(keys) == len(set(keys)) == 2


@pytest.mark.parametrize("solver", SOLVERS)
def test_infeasible_mandatory(solver):
    cs = [cand(1, 0, minutes=600, mandatory=True), cand(2, 1, minutes=30)]
    res = optimize(spec(cs, start=9 * 60, end=17 * 60), straight_fn, solver)
    assert res.status == "infeasible"
    assert 1 in [u.key for u in res.unscheduled]
    assert any(i.code in ("no_feasible_day", "mandatory_exceeds_capacity") for i in res.issues)
    assert order(res) == [2]


def test_all_mandatory_over_capacity_is_reported():
    cs = [cand(i, i, minutes=300, mandatory=True) for i in (1, 2)]
    res = optimize(spec(cs, start=9 * 60, end=17 * 60), straight_fn)
    assert res.status == "infeasible"
    assert any(i.code == "mandatory_exceeds_capacity" for i in res.issues)
    assert any(i.code == "mandatory_unscheduled" for i in res.issues)


def test_missing_routing_is_labelled_not_timed():
    cs = [cand(1, 0), cand(2, 2)]
    res = optimize(spec(cs, transit_buffer_minutes=10), straight_fn)
    assert res.matrix_kind == "straight_line_estimate"
    assert res.metrics["travel_minutes"] is None
    assert res.metrics["distance_kind"] == "straight_line_estimate"
    assert "Not a route" in res.metrics["distance_note"]
    second = res.days[0].stops[1]
    assert second.travel_basis == "user_buffer" and second.travel_minutes == 10
    assert second.distance_kind == "straight_line_estimate"
    assert any(i.code == "no_routing" for i in res.issues)


def test_routed_minutes_come_from_matrix():
    cs = [cand(1, 0), cand(2, 1.2)]  # ~1.2 km at 1.2 m/s ~ 1000 s ~ 17 min
    s = spec(cs, transit_buffer_minutes=0)
    res = optimize(s, routed_fn(speed_mps=1.2), "fallback")
    leg = res.days[0].stops[1]
    assert leg.travel_basis == "routed"
    assert 15 <= leg.travel_minutes <= 19
    assert res.metrics["distance_kind"] == "routed"


def test_unreachable_pair_not_used_when_alternative_exists():
    cs = [cand(1, 0), cand(2, 1), cand(3, 2)]
    fn = routed_fn(overrides={("p1", "p2"): None})
    res = optimize(spec(cs, start_point=P(-0.2)), fn, "ortools")
    o = order(res)
    assert o.index(1) + 1 != o.index(2) or o.index(1) > o.index(2)


@pytest.mark.parametrize("solver", SOLVERS)
def test_opening_hours_wait_and_closed_day(solver):
    afternoon = parse_hours({d: [["14:00", "16:00"]] for d in ["mon"]})
    only_tuesday = parse_hours({"tue": [["09:00", "17:00"]]})
    cs = [cand(1, 0, minutes=60, hours=afternoon), cand(2, 0.5, minutes=60, hours=only_tuesday)]
    res = optimize(spec(cs, n_days=1), straight_fn, solver)  # day 0 is a Monday
    st = res.days[0].stops
    assert [s.key for s in st] == [1]
    assert st[0].start == 14 * 60 and st[0].wait > 0
    assert [u.key for u in res.unscheduled] == [2]
    assert res.unscheduled[0].code == "closed"
    res2 = optimize(spec(cs, n_days=2), straight_fn, solver)
    assert order(res2, 1) == [2]


def test_lunch_break_windows_respected():
    h = parse_hours({"mon": [["09:00", "12:00"], ["15:00", "18:00"]]})
    cs = [cand(1, 0, minutes=120, hours=h), cand(2, 0.01, minutes=190, name="Long")]
    res = optimize(spec(cs, start=11 * 60, end=18 * 60, transit_buffer_minutes=0), straight_fn, "ortools")
    st = {s.key: s for s in res.days[0].stops}
    if 1 in st:
        assert st[1].start >= 15 * 60 or st[1].end <= 12 * 60


@pytest.mark.parametrize("solver", SOLVERS)
def test_max_daily_workload(solver):
    cs = [cand(i, i * 0.1, minutes=120, interest=3) for i in range(1, 5)]
    res = optimize(spec(cs, max_daily_minutes=250, transit_buffer_minutes=0), straight_fn, solver)
    assert len(order(res)) == 2
    assert res.days[0].visit_minutes <= 250


@pytest.mark.parametrize("solver", SOLVERS)
def test_multi_day_spreads_load(solver):
    cs = [cand(i, i * 0.5, minutes=120) for i in range(1, 5)]
    res = optimize(spec(cs, n_days=2, max_daily_minutes=300), straight_fn, solver)
    assert sorted(order(res, 0) + order(res, 1)) == [1, 2, 3, 4]
    assert order(res, 0) and order(res, 1)


@pytest.mark.parametrize("solver", SOLVERS)
def test_locked_stop_stays_on_day_and_order(solver):
    cs = [
        cand(1, 0, locked_day=1, locked_order=1),
        cand(2, 0.1, locked_day=1, locked_order=0),
        cand(3, 0.2),
    ]
    res = optimize(spec(cs, n_days=2), straight_fn, solver)
    day1 = order(res, 1)
    assert day1.index(2) < day1.index(1)
    assert 1 not in order(res, 0) and 2 not in order(res, 0)


@pytest.mark.parametrize("solver", SOLVERS)
def test_pinned_day(solver):
    cs = [cand(1, 0, pinned_day=1), cand(2, 0.1)]
    res = optimize(spec(cs, n_days=2), straight_fn, solver)
    assert 1 in order(res, 1)


def test_deterministic_for_identical_input():
    cs = [cand(i, (i * 7) % 5, (i * 3) % 4, minutes=45 + i) for i in range(1, 9)]
    a = optimize(spec(cs, n_days=2), routed_fn(), "ortools")
    b = optimize(spec(list(reversed(cs)), n_days=2), routed_fn(), "ortools")
    assert [order(a, d) for d in (0, 1)] == [order(b, d) for d in (0, 1)]


def test_budget_defers_optional_and_ignores_other_currency():
    cs = [
        cand(1, 0, interest=5, cost=D("40"), cost_currency="EUR"),
        cand(2, 0.1, interest=4, cost=D("40"), cost_currency="EUR"),
        cand(3, 0.2, interest=3, cost=D("5"), cost_currency="USD"),
        cand(4, 0.3, interest=2),
    ]
    s = spec(cs, travelers=2, budget=D("100"), currency="EUR")
    sel = select_places(s)
    assert [c.key for c in sel.selected] == [1, 3, 4]
    assert sel.deferred[0].key == 2 and sel.deferred[0].code == "budget"
    assert sel.spend == D("80")
    codes = {i.code for i in sel.issues}
    assert {"currency_mismatch", "cost_unknown"} <= codes


def test_budget_exceeded_by_mandatory_is_error():
    cs = [cand(1, 0, mandatory=True, cost=D("90"), cost_currency="EUR")]
    res = optimize(spec(cs, travelers=2, budget=D("100")), straight_fn)
    assert res.status == "infeasible"
    assert any(i.code == "budget_exceeded" for i in res.issues)


def test_validate_spec_catches_bad_input():
    cs = [cand(1, 0, minutes=0), cand(2, 0, pinned_day=9)]
    codes = {i.code for i in validate_spec(spec(cs))}
    assert {"bad_duration", "bad_day"} <= codes


def test_ortools_not_worse_than_fallback_on_line():
    cs = [cand(i, i) for i in (5, 2, 4, 1, 3)]
    a = optimize(spec(cs, start_point=P(-0.1)), routed_fn(), "ortools")
    b = optimize(spec(cs, start_point=P(-0.1)), routed_fn(), "fallback")
    assert a.metrics["distance_m"] <= b.metrics["distance_m"] + 1


def test_before_after_baseline_metrics():
    cs = [cand(1, 0), cand(2, 1), cand(3, 2)]
    res = optimize(spec(cs, start_point=P(-0.1)), routed_fn(), "ortools", baseline={0: [3, 1, 2]})
    assert res.metrics["before"]["distance_m"] > res.metrics["distance_m"]


def test_schedule_only_preserves_order_and_flags_problems():
    cs = [cand(1, 0, minutes=200), cand(2, 1, minutes=200), cand(3, 2, minutes=200)]
    res = schedule_only(spec(cs, start=9 * 60, end=17 * 60), straight_fn, {0: [3, 1, 2]})
    assert order(res) == [3, 1, 2]
    assert res.status == "infeasible"
    assert any(i.code == "schedule_day_end" for i in res.issues)


def test_matrix_validation():
    with pytest.raises(ValueError):
        TravelMatrix(["a", "b"], "routed", [[0, 1], [1, 0]], None)
    with pytest.raises(ValueError):
        TravelMatrix(["a"], "straight_line_estimate", [[0]], [[0]])


@pytest.mark.parametrize("solver", SOLVERS)
def test_selected_places_are_kept_when_time_allows_even_with_long_legs(solver):
    # six places 3-5 km apart (~35-60 min walking legs); two full days available
    cs = [cand(i, (i * 4) % 9, (i * 7) % 11, minutes=60) for i in range(1, 7)]
    res = optimize(spec(cs, n_days=2, transit_buffer_minutes=15), routed_fn(detour=1.3), solver)
    assert res.unscheduled == []
    assert sum(len(d.stops) for d in res.days) == 6
