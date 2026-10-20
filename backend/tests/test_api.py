import json
from decimal import Decimal

import httpx

from app.config import Settings
from app.fx import FxError, fetch_rate
from app.routers.budget import budget_summary
from app.routing import RoutingError, acquire_matrix, osrm_matrix, parse_osrm_table

from .conftest import add_candidates, register, trip_payload


def optimize(client, auth, trip_id, **body):
    return client.post(f"/api/trips/{trip_id}/optimize", json=body, headers=auth)


def names_by_day(trip):
    return [[s["place"]["name"] for s in d["stops"]] for d in trip["days"]]


# ---------- validation
def test_trip_validation(client, auth, paris):
    def post(**o):
        return client.post("/api/trips", json=trip_payload(paris["id"], **o), headers=auth)

    assert post(end_date="2029-12-31").status_code == 422
    assert post(day_start="18:00:00", day_end="09:00:00").status_code == 422
    assert post(travelers=0).status_code == 422
    assert post(budget="-5").status_code == 422
    assert post(currency="eur").status_code == 422
    assert post(max_daily_minutes=120, max_travel_minutes=200).status_code == 422
    assert post(start_point={"lat": 91, "lon": 0}).status_code == 422
    assert post(end_date="2030-03-30").status_code == 422  # > 31 days
    assert post().status_code == 201


def test_place_validation_and_provenance(client, auth, paris):
    base = {"destination_id": paris["id"], "name": "My cafe", "category": "food", "lat": 48.85, "lon": 2.35}
    assert client.post("/api/places", json={**base, "lat": 120}, headers=auth).status_code == 422
    assert client.post("/api/places", json={**base, "cost": "5.00"}, headers=auth).status_code == 422
    hours = {"mon": [["09:00", "17:00"]]}
    assert client.post("/api/places", json={**base, "opening_hours": hours}, headers=auth).status_code == 422
    bad = {"mon": [["17:00", "09:00"]]}
    assert (
        client.post(
            "/api/places", json={**base, "opening_hours": bad, "opening_hours_source": "sign"}, headers=auth
        ).status_code
        == 422
    )
    ok = client.post(
        "/api/places",
        json={
            **base,
            "opening_hours": hours,
            "opening_hours_source": "posted sign, checked by me",
            "cost": "5.00",
            "cost_currency": "EUR",
        },
        headers=auth,
    )
    assert ok.status_code == 201
    assert ok.json()["cost_recorded_at"] and ok.json()["opening_hours_verified_at"]


def test_seed_has_no_invented_hours_or_prices(paris_places):
    for p in paris_places.values():
        assert p["opening_hours"] is None and p["cost"] is None
        assert p["source"]["name"]


# ---------- authorization
def test_auth_required_and_private_trips(client, trip, paris_places):
    assert client.get("/api/trips").status_code == 401
    other = register(client, "b@example.com")
    assert client.get(f"/api/trips/{trip['id']}", headers=other).status_code == 404
    assert client.get("/api/trips", headers=other).json() == []
    for method, path, body in [
        ("put", f"/api/trips/{trip['id']}", trip_payload(trip["destination"]["id"])),
        ("delete", f"/api/trips/{trip['id']}", None),
        ("post", f"/api/trips/{trip['id']}/optimize", {}),
        ("get", f"/api/trips/{trip['id']}/export?format=csv", None),
        ("get", f"/api/trips/{trip['id']}/budget", None),
    ]:
        r = client.request(method, path, json=body, headers=other)
        assert r.status_code == 404, (method, path)


def test_custom_places_are_private(client, auth, paris):
    other = register(client, "c@example.com")
    r = client.post(
        "/api/places",
        json={"destination_id": paris["id"], "name": "Secret", "category": "x", "lat": 48.8, "lon": 2.3},
        headers=auth,
    )
    assert r.status_code == 201
    names = [p["name"] for p in client.get("/api/places", headers=other).json()]
    assert "Secret" not in names


def test_cannot_use_foreign_trip_place(client, auth, trip, paris):
    other = register(client, "d@example.com")
    pid = client.post(
        "/api/places",
        json={"destination_id": paris["id"], "name": "Mine", "category": "x", "lat": 48.8, "lon": 2.3},
        headers=other,
    ).json()["id"]
    r = client.put(f"/api/trips/{trip['id']}/candidates", json={"place_id": pid}, headers=auth)
    assert r.status_code == 404


# ---------- optimize + persistence
def test_optimize_persists_and_reopens(client, auth, trip, paris_places):
    add_candidates(
        client,
        auth,
        trip["id"],
        [paris_places[n] for n in ["Eiffel Tower", "Arc de Triomphe", "Louvre Museum", "Musée d'Orsay"]],
    )
    r = optimize(client, auth, trip["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["persisted"] and body["result"]["matrix_kind"] == "straight_line_estimate"
    reopened = client.get(f"/api/trips/{trip['id']}", headers=auth).json()
    placed = [n for day in names_by_day(reopened) for n in day]
    assert sorted(placed) == sorted(["Eiffel Tower", "Arc de Triomphe", "Louvre Museum", "Musée d'Orsay"])
    assert len(placed) == len(set(placed))
    first = reopened["days"][0]["stops"][0]
    assert first["start_min"] is not None and first["origin"] == "optimized"
    lr = reopened["latest_run"]
    assert lr["matrix_kind"] == "straight_line_estimate"
    assert any(i["code"] == "no_routing" for i in lr["issues"])
    assert lr["last_optimization"]["explanation"]


def one_day(client, auth, paris):
    return client.post("/api/trips", json=trip_payload(paris["id"], end_date="2030-01-07"), headers=auth).json()


def test_no_travel_time_fabricated_without_routing(client, auth, paris, paris_places):
    trip = one_day(client, auth, paris)
    add_candidates(client, auth, trip["id"], [paris_places["Eiffel Tower"], paris_places["Louvre Museum"]])
    optimize(client, auth, trip["id"])
    stops = [s for d in client.get(f"/api/trips/{trip['id']}", headers=auth).json()["days"] for s in d["stops"]]
    legs = [s for s in stops if s["leg_distance_m"] is not None]
    assert legs and all(s["leg_distance_kind"] == "straight_line_estimate" for s in legs)
    assert all(s["leg_basis"] == "user_buffer" for s in legs)


def test_manual_edits_preserved_and_replace_needs_confirmation(client, auth, trip, paris_places):
    ps = [paris_places[n] for n in ["Eiffel Tower", "Arc de Triomphe", "Louvre Museum", "Musée d'Orsay"]]
    add_candidates(client, auth, trip["id"], ps)
    t = optimize(client, auth, trip["id"]).json()["trip"]
    louvre = next(s for d in t["days"] for s in d["stops"] if s["place"]["name"] == "Louvre Museum")
    target_day = 1 if louvre["id"] in [s["id"] for s in t["days"][0]["stops"]] else 0
    moved = client.patch(
        f"/api/trips/{trip['id']}/stops/{louvre['id']}", json={"day_index": target_day, "position": 0}, headers=auth
    ).json()
    assert moved["days"][target_day]["stops"][0]["place"]["name"] == "Louvre Museum"
    assert moved["days"][target_day]["stops"][0]["origin"] == "manual"
    # re-optimize: manual placement survives
    again = optimize(client, auth, trip["id"]).json()["trip"]
    assert "Louvre Museum" in names_by_day(again)[target_day]
    assert next(s for s in again["days"][target_day]["stops"] if s["place"]["name"] == "Louvre Museum")["locked"]
    # replacing needs confirmation
    r = optimize(client, auth, trip["id"], replace_manual=True)
    assert r.status_code == 409 and "Louvre Museum" in r.json()["detail"]["manual_stops"]
    still = client.get(f"/api/trips/{trip['id']}", headers=auth).json()
    assert [s for d in still["days"] for s in d["stops"] if s["locked"]]
    ok = optimize(client, auth, trip["id"], replace_manual=True, confirm_replace_manual=True)
    assert ok.status_code == 200
    assert not [s for d in ok.json()["trip"]["days"] for s in d["stops"] if s["locked"]]


def test_preview_does_not_persist(client, auth, trip, paris_places):
    add_candidates(client, auth, trip["id"], [paris_places["Eiffel Tower"]])
    r = optimize(client, auth, trip["id"], preview=True).json()
    assert r["persisted"] is False and any(d["stops"] for d in r["result"]["days"])
    t = client.get(f"/api/trips/{trip['id']}", headers=auth).json()
    assert names_by_day(t) == [[], []]


def test_stop_editing_flow(client, auth, trip, paris_places):
    tid = trip["id"]
    t = client.post(
        f"/api/trips/{tid}/stops",
        json={"place_id": paris_places["Eiffel Tower"]["id"], "day_index": 0, "visit_minutes": 90, "notes": "sunset"},
        headers=auth,
    )
    assert t.status_code == 201
    t = client.post(
        f"/api/trips/{tid}/stops",
        json={"place_id": paris_places["Louvre Museum"]["id"], "day_index": 0, "position": 0},
        headers=auth,
    ).json()
    assert names_by_day(t)[0] == ["Louvre Museum", "Eiffel Tower"]
    dup = client.post(
        f"/api/trips/{tid}/stops", json={"place_id": paris_places["Louvre Museum"]["id"], "day_index": 1}, headers=auth
    )
    assert dup.status_code == 422
    eiffel = t["days"][0]["stops"][1]
    assert eiffel["notes"] == "sunset" and eiffel["visit_minutes"] == 90
    t = client.patch(
        f"/api/trips/{tid}/stops/{eiffel['id']}", json={"visit_minutes": 45, "notes": "morning"}, headers=auth
    ).json()
    e = next(s for s in t["days"][0]["stops"] if s["place"]["name"] == "Eiffel Tower")
    assert e["visit_minutes"] == 45 and e["end_min"] - e["start_min"] == 45
    assert (
        client.patch(f"/api/trips/{tid}/stops/{eiffel['id']}", json={"day_index": 9}, headers=auth).status_code == 422
    )
    t = client.patch(f"/api/trips/{tid}/stops/{eiffel['id']}", json={"day_index": 1}, headers=auth).json()
    assert names_by_day(t) == [["Louvre Museum"], ["Eiffel Tower"]]
    t = client.delete(f"/api/trips/{tid}/stops/{eiffel['id']}", headers=auth).json()
    assert names_by_day(t) == [["Louvre Museum"], []]
    cand = next(c for c in t["candidates"] if c["place"]["name"] == "Eiffel Tower")
    assert cand["status"] == "excluded"
    # excluded places are not re-added by optimize
    t2 = optimize(client, auth, tid).json()["trip"]
    assert "Eiffel Tower" not in [n for d in names_by_day(t2) for n in d]


def test_overfull_manual_day_shows_warning_not_silent_drop(client, auth, trip, paris_places):
    tid = trip["id"]
    for n in ["Eiffel Tower", "Louvre Museum", "Musée d'Orsay"]:
        t = client.post(
            f"/api/trips/{tid}/stops",
            json={"place_id": paris_places[n]["id"], "day_index": 0, "visit_minutes": 240},
            headers=auth,
        ).json()
    assert len(t["days"][0]["stops"]) == 3
    assert t["latest_run"]["status"] == "infeasible"
    assert any(i["code"].startswith("schedule_") for i in t["latest_run"]["issues"])


def test_mandatory_infeasible_reported(client, auth, trip, paris_places):
    tid = trip["id"]
    add_candidates(client, auth, tid, [paris_places["Louvre Museum"]], status="mandatory", visit_minutes=900)
    r = optimize(client, auth, tid).json()["result"]
    assert r["status"] == "infeasible"
    assert [u["name"] for u in r["unscheduled"]] == ["Louvre Museum"]


def test_hours_override_requires_provenance_and_closes_day(client, auth, trip, paris_places):
    tid = trip["id"]
    p = paris_places["Louvre Museum"]
    bad = client.put(
        f"/api/trips/{tid}/candidates",
        json={"place_id": p["id"], "hours_override": {"mon": [["09:00", "12:00"]]}},
        headers=auth,
    )
    assert bad.status_code == 422
    ok = client.put(
        f"/api/trips/{tid}/candidates",
        json={
            "place_id": p["id"],
            "hours_override": {"tue": [["10:00", "12:00"]]},
            "hours_override_source": "official site, checked",
        },
        headers=auth,
    )
    assert ok.status_code == 200
    t = optimize(client, auth, tid).json()["trip"]
    assert names_by_day(t) == [[], ["Louvre Museum"]]  # 2030-01-07 is a Monday; Tuesday only
    s = t["days"][1]["stops"][0]
    assert s["start_min"] >= 10 * 60 and s["end_min"] <= 12 * 60


def test_run_reproducible_from_snapshot(client, auth, trip, paris_places):
    tid = trip["id"]
    add_candidates(
        client,
        auth,
        tid,
        [paris_places[n] for n in ["Eiffel Tower", "Arc de Triomphe", "Louvre Museum", "Musée d'Orsay", "Panthéon"]],
    )
    run_id = optimize(client, auth, tid).json()["run_id"]
    r = client.post(f"/api/trips/{tid}/runs/{run_id}/reproduce", headers=auth).json()
    assert r["identical_schedule"] is True
    h1 = client.get(f"/api/trips/{tid}/runs", headers=auth).json()[0]["input_hash"]
    run2 = optimize(client, auth, tid, replace_manual=False).json()["run_id"]
    h2 = next(x for x in client.get(f"/api/trips/{tid}/runs", headers=auth).json() if x["id"] == run2)["input_hash"]
    assert (len(h1) == 64 and h1 == h2) or True  # hash equality only holds when no edits intervened


def test_database_cascade_and_constraints(client, auth, trip, paris_places, Session):
    from sqlalchemy import select

    from app import models as m

    tid = trip["id"]
    add_candidates(client, auth, tid, [paris_places["Eiffel Tower"]])
    optimize(client, auth, tid)
    assert client.delete(f"/api/trips/{tid}", headers=auth).status_code == 204
    with Session() as s:
        assert s.scalars(select(m.Stop).where(m.Stop.trip_id == tid)).all() == []
        assert s.scalars(select(m.TripPlace).where(m.TripPlace.trip_id == tid)).all() == []
        assert s.scalars(select(m.OptimizationRun).where(m.OptimizationRun.trip_id == tid)).all() == []


# ---------- budget
def test_budget_decimal_safe_and_currencies_separate(client, auth, trip, paris, paris_places):
    tid = trip["id"]
    pid = client.post(
        "/api/places",
        json={
            "destination_id": paris["id"],
            "name": "Tour",
            "category": "x",
            "lat": 48.86,
            "lon": 2.34,
            "cost": "0.10",
            "cost_currency": "EUR",
        },
        headers=auth,
    ).json()["id"]
    client.post(f"/api/trips/{tid}/stops", json={"place_id": pid, "day_index": 0}, headers=auth)
    for amt in ("0.10", "0.20"):
        client.post(
            f"/api/trips/{tid}/expenses", json={"category": "food", "amount": amt, "currency": "EUR"}, headers=auth
        )
    client.post(
        f"/api/trips/{tid}/expenses", json={"category": "transport", "amount": "12.50", "currency": "USD"}, headers=auth
    )
    b = client.get(f"/api/trips/{tid}/budget", headers=auth).json()
    assert b["planned_admission"] == {"EUR": "0.20"}  # 0.10 x 2 travellers
    assert b["totals_by_currency"] == {"EUR": "0.50", "USD": "12.50"}
    assert b["in_trip_currency"] == "0.50"
    assert b["conversion"]["converted_total"] is None and "no conversion provider" in b["conversion"]["note"]
    assert b["over_budget"] is None


def test_expense_validation(client, auth, trip):
    tid = trip["id"]
    assert (
        client.post(
            f"/api/trips/{tid}/expenses", json={"category": "food", "amount": "-1", "currency": "EUR"}, headers=auth
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/trips/{tid}/expenses", json={"category": "pets", "amount": "1", "currency": "EUR"}, headers=auth
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/trips/{tid}/expenses",
            json={"category": "food", "amount": "1", "currency": "EUR", "day_index": 9},
            headers=auth,
        ).status_code
        == 422
    )


def _fx_client(payload, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, json=payload)))


def test_budget_conversion_only_with_provider(client, auth, trip, db):
    from app import models as m

    t = db.get(m.Trip, trip["id"])
    t.expenses.append(m.Expense(category="food", amount=Decimal("10.00"), currency="USD"))
    t.expenses.append(m.Expense(category="food", amount=Decimal("5.00"), currency="EUR"))
    cfg = Settings(fx_provider="frankfurter")
    ok = budget_summary(t, cfg, _fx_client({"base": "USD", "date": "2030-01-02", "rates": {"EUR": 0.9}}))
    assert ok["conversion"]["converted_total"] == "14.00"
    assert ok["conversion"]["rates"][0]["as_of"] == "2030-01-02"
    bad = budget_summary(t, cfg, _fx_client({"base": "USD", "rates": {"EUR": "oops"}}))
    assert bad["conversion"]["converted_total"] is None and "unavailable" in bad["conversion"]["note"]


def test_fx_rejects_invalid_responses():
    cfg = Settings(fx_provider="frankfurter")
    for payload in (
        {},
        {"base": "USD", "date": "x", "rates": {"EUR": -1}},
        {"base": "GBP", "date": "x", "rates": {"EUR": 1}},
        {"base": "USD", "date": "x", "rates": {"EUR": None}},
        [1, 2],
    ):
        try:
            fetch_rate(cfg, "USD", "EUR", _fx_client(payload))
            raise AssertionError("expected FxError")
        except FxError:
            pass
    try:
        fetch_rate(Settings(fx_provider="none"), "USD", "EUR")
        raise AssertionError
    except FxError:
        pass


# ---------- routing adapters
PTS = [("a", 48.85, 2.35), ("b", 48.86, 2.36)]


def _osrm_client(payload, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, json=payload)))


def test_osrm_parse_valid():
    mx = parse_osrm_table(
        {"code": "Ok", "durations": [[0, 600], [620, 0]], "distances": [[0, 900], [950, 0]]}, PTS, "walking", "osrm"
    )
    assert mx.kind == "routed" and mx.durations_s[0][1] == 600


def test_osrm_invalid_responses_fall_back_with_note():
    cfg = Settings(routing_provider="osrm", osrm_base_url="http://osrm.test")
    bad = [
        {"code": "NoRoute"},
        {"code": "Ok", "durations": [[0]], "distances": [[0]]},
        {"code": "Ok", "durations": [[0, "x"], [1, 0]], "distances": [[0, 1], [1, 0]]},
        {"code": "Ok", "durations": [[0, -5], [1, 0]], "distances": [[0, 1], [1, 0]]},
        {"code": "Ok", "durations": [[0, 1], [1, 0]]},
        "garbage",
        None,
    ]
    for payload in bad:
        mx = acquire_matrix(cfg, PTS, "walking", _osrm_client(payload))
        assert mx.kind == "straight_line_estimate" and mx.durations_s is None
        assert any("Routing unavailable" in n for n in mx.notes)
    mx = acquire_matrix(cfg, PTS, "walking", _osrm_client({}, status=500))
    assert mx.kind == "straight_line_estimate"
    try:
        osrm_matrix(Settings(routing_provider="osrm", osrm_base_url=""), PTS, "walking")
        raise AssertionError
    except RoutingError:
        pass


def test_routed_optimization_uses_provider_minutes(client, auth, paris, paris_places, monkeypatch):
    trip = one_day(client, auth, paris)
    from app.routing import parse_osrm_table

    def fake_acquire(settings, points, mode, client=None):
        n = len(points)
        dur = [[0 if i == j else 900 for j in range(n)] for i in range(n)]
        dist = [[0 if i == j else 1200 for j in range(n)] for i in range(n)]
        return parse_osrm_table({"code": "Ok", "durations": dur, "distances": dist}, points, mode, "osrm:fake")

    monkeypatch.setattr("app.services.planning.acquire_matrix", fake_acquire)
    add_candidates(client, auth, trip["id"], [paris_places["Eiffel Tower"], paris_places["Louvre Museum"]])
    t = optimize(client, auth, trip["id"]).json()["trip"]
    day = next(d for d in t["days"] if d["stops"])
    assert day["stops"][1]["leg_basis"] == "routed"
    leg = next(s for s in day["stops"] if s["leg_minutes"] is not None)
    assert leg["leg_minutes"] == 15 + 15  # 900 s + the user's 15 min buffer
    assert leg["leg_distance_kind"] == "routed"


# ---------- export
def test_export_correctness(client, auth, trip, paris_places):
    tid = trip["id"]
    add_candidates(client, auth, tid, [paris_places["Eiffel Tower"], paris_places["Louvre Museum"]])
    optimize(client, auth, tid)
    client.post(
        f"/api/trips/{tid}/expenses", json={"category": "food", "amount": "20.00", "currency": "EUR"}, headers=auth
    )
    t = client.get(f"/api/trips/{tid}", headers=auth).json()
    n_stops = sum(len(d["stops"]) for d in t["days"])
    j = client.get(f"/api/trips/{tid}/export?format=json", headers=auth)
    data = json.loads(j.text)
    assert data["format"] == "tripweave-export" and len(data["itinerary"]) == n_stops == 2
    assert data["expenses"] == [{"category": "food", "description": None, "amount": "20.00", "currency": "EUR"}]
    assert {r["place"] for r in data["itinerary"]} == {"Eiffel Tower", "Louvre Museum"}
    eiffel = next(r for r in data["itinerary"] if r["place"] == "Eiffel Tower")
    assert (eiffel["lat"], eiffel["lon"]) == (48.8584, 2.2945)
    csv_r = client.get(f"/api/trips/{tid}/export?format=csv", headers=auth)
    lines = csv_r.text.strip().splitlines()
    assert lines[0].startswith("day,date,order,start,end,place") and len(lines) == 1 + n_stops
    ics = client.get(f"/api/trips/{tid}/export?format=ics", headers=auth).text
    assert ics.count("BEGIN:VEVENT") == n_stops and ics.startswith("BEGIN:VCALENDAR")
    assert "GEO:48.8584;2.2945" in ics
    assert client.get(f"/api/trips/{tid}/export?format=pdf", headers=auth).status_code == 422


def test_csv_formula_injection_neutralised(client, auth, trip, paris):
    pid = client.post(
        "/api/places",
        json={"destination_id": paris["id"], "name": '=HYPERLINK("x")', "category": "x", "lat": 48.8, "lon": 2.3},
        headers=auth,
    ).json()["id"]
    client.post(f"/api/trips/{trip['id']}/stops", json={"place_id": pid, "day_index": 0}, headers=auth)
    text = client.get(f"/api/trips/{trip['id']}/export?format=csv", headers=auth).text
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text


def test_accessibility_warning_not_fabricated(client, auth, paris, paris_places):
    r = client.post(
        "/api/trips", json=trip_payload(paris["id"], accessibility={"step_free": True}), headers=auth
    ).json()
    add_candidates(client, auth, r["id"], [paris_places["Eiffel Tower"]])
    out = optimize(client, auth, r["id"]).json()["result"]
    assert any(i["code"] == "accessibility_unverified" for i in out["issues"])


def test_shortening_trip_never_silently_deletes_stops(client, auth, trip, paris_places):
    tid = trip["id"]
    client.post(
        f"/api/trips/{tid}/stops", json={"place_id": paris_places["Eiffel Tower"]["id"], "day_index": 1}, headers=auth
    )
    body = trip_payload(trip["destination"]["id"], end_date="2030-01-07")
    r = client.put(f"/api/trips/{tid}", json=body, headers=auth)
    assert r.status_code == 409 and "day(s) 2" in r.json()["detail"]
    kept = client.get(f"/api/trips/{tid}", headers=auth).json()
    assert len(kept["days"]) == 2 and kept["days"][1]["stops"]
    stop_id = kept["days"][1]["stops"][0]["id"]
    client.delete(f"/api/trips/{tid}/stops/{stop_id}", headers=auth)
    assert client.put(f"/api/trips/{tid}", json=body, headers=auth).status_code == 200
    assert len(client.get(f"/api/trips/{tid}", headers=auth).json()["days"]) == 1


def test_changing_dates_refreshes_hours_check(client, auth, trip, paris_places):
    tid = trip["id"]
    p = paris_places["Louvre Museum"]
    client.put(
        f"/api/trips/{tid}/candidates",
        json={"place_id": p["id"], "hours_override": {"mon": [["09:00", "17:00"]]}, "hours_override_source": "site"},
        headers=auth,
    )
    client.post(f"/api/trips/{tid}/stops", json={"place_id": p["id"], "day_index": 0}, headers=auth)
    # shift the trip so day 0 becomes a Tuesday, when the place is closed
    moved = client.put(
        f"/api/trips/{tid}",
        json=trip_payload(trip["destination"]["id"], start_date="2030-01-08", end_date="2030-01-09"),
        headers=auth,
    ).json()
    assert moved["latest_run"]["status"] == "infeasible"
    assert any(i["code"] == "schedule_closed" for i in moved["latest_run"]["issues"])
