from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models as m
from ..config import Settings
from ..db import get_db
from ..deps import current_user, owned_trip, settings_dep
from ..schemas import (
    CandidateIn,
    CandidateOut,
    CandidatePatch,
    OptimizeIn,
    PinIn,
    StopCreate,
    StopPatch,
    TripIn,
    TripOut,
    TripSummary,
)
from ..services import planning

router = APIRouter(prefix="/api/trips", tags=["trips"])


def trip_out(db: Session, trip: m.Trip) -> TripOut:
    out = TripOut.model_validate(trip)
    out.pins = [PinIn(**c.value) for c in trip.constraints if c.kind == "pin_day"]
    runs = list(trip.runs)
    if runs:
        newest = runs[-1]
        last_opt = next((r for r in reversed(runs) if r.kind == "optimize"), None)
        out.latest_run = {
            "id": newest.id,
            "kind": newest.kind,
            "created_at": newest.created_at.isoformat(),
            "status": newest.status,
            "matrix_kind": newest.matrix_kind,
            "matrix_provider": newest.matrix_provider,
            "issues": newest.result.get("issues", []),
            "metrics": newest.result.get("metrics", {}),
            "last_optimization": None
            if last_opt is None
            else {
                "id": last_opt.id,
                "created_at": last_opt.created_at.isoformat(),
                "solver": last_opt.solver,
                "explanation": last_opt.result.get("explanation", []),
                "unscheduled": last_opt.result.get("unscheduled", []),
                "metrics": last_opt.result.get("metrics", {}),
                "params": last_opt.params,
                "input_hash": last_opt.input_hash,
            },
        }
    return out


def _load(db: Session, trip_id: int) -> m.Trip:
    trip = db.scalar(
        select(m.Trip)
        .where(m.Trip.id == trip_id)
        .execution_options(populate_existing=True)
        .options(
            selectinload(m.Trip.days).selectinload(m.TripDay.stops).selectinload(m.Stop.place),
            selectinload(m.Trip.candidates).selectinload(m.TripPlace.place),
        )
    )
    assert trip is not None
    return trip


def _apply(trip: m.Trip, body: TripIn) -> None:
    for k, v in body.model_dump(exclude={"accessibility", "start_point", "end_point"}).items():
        setattr(trip, k, v)
    trip.accessibility = body.accessibility.model_dump() if body.accessibility else None
    trip.start_point = body.start_point.model_dump() if body.start_point else None
    trip.end_point = body.end_point.model_dump() if body.end_point else None


@router.get("", response_model=list[TripSummary])
def list_trips(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(m.Trip)
        .where(m.Trip.owner_id == user.id)
        .options(selectinload(m.Trip.destination))
        .order_by(m.Trip.updated_at.desc())
    ).all()


@router.post("", response_model=TripOut, status_code=201)
def create_trip(body: TripIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(m.Destination, body.destination_id) is None:
        raise HTTPException(404, "Destination not found")
    trip = m.Trip(owner_id=user.id)
    _apply(trip, body)
    db.add(trip)
    db.flush()
    planning.ensure_days(db, trip)
    db.commit()
    return trip_out(db, _load(db, trip.id))


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db)):
    return trip_out(db, _load(db, trip.id))


@router.put("/{trip_id}", response_model=TripOut)
def update_trip(
    body: TripIn,
    trip: m.Trip = Depends(owned_trip),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
):
    if db.get(m.Destination, body.destination_id) is None:
        raise HTTPException(404, "Destination not found")
    _apply(trip, body)
    try:
        planning.ensure_days(db, trip)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    if any(d.stops for d in trip.days):
        planning.retime(db, trip, settings)  # weekdays/limits may have changed: refresh warnings
    return trip_out(db, _load(db, trip.id))


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db)):
    db.delete(trip)
    db.commit()
    return Response(status_code=204)


# ---- candidate pool
@router.put("/{trip_id}/candidates", response_model=CandidateOut)
def upsert_candidate(
    body: CandidateIn,
    trip: m.Trip = Depends(owned_trip),
    user: m.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    place = planning.get_place_for_user(db, user.id, body.place_id)
    if place is None:
        raise HTTPException(404, "Place not found")
    if place.destination_id != trip.destination_id:
        raise HTTPException(422, "Place belongs to a different destination than the trip")
    tp = planning.ensure_candidate(db, trip, place)
    data = body.model_dump(exclude_unset=True, exclude={"place_id"})
    for k, v in data.items():
        setattr(tp, k, v)
    db.commit()
    db.refresh(tp)
    return tp


@router.patch("/{trip_id}/candidates/{place_id}", response_model=CandidateOut)
def patch_candidate(
    place_id: int, body: CandidatePatch, trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db)
):
    tp = next((c for c in trip.candidates if c.place_id == place_id), None)
    if tp is None:
        raise HTTPException(404, "Candidate not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(tp, k, v)
    if "visit_minutes" in body.model_fields_set and body.visit_minutes:
        for d in trip.days:
            for s in d.stops:
                if s.place_id == place_id:
                    s.visit_minutes = body.visit_minutes
    db.commit()
    db.refresh(tp)
    return tp


@router.delete("/{trip_id}/candidates/{place_id}", status_code=204)
def delete_candidate(place_id: int, trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db)):
    tp = next((c for c in trip.candidates if c.place_id == place_id), None)
    if tp is None:
        raise HTTPException(404, "Candidate not found")
    for d in trip.days:
        for s in list(d.stops):
            if s.place_id == place_id:
                d.stops.remove(s)
                db.delete(s)
    trip.constraints[:] = [
        c for c in trip.constraints if not (c.kind == "pin_day" and c.value.get("place_id") == place_id)
    ]
    trip.candidates.remove(tp)
    db.commit()
    return Response(status_code=204)


@router.put("/{trip_id}/pins", response_model=list[PinIn])
def set_pin(body: PinIn, trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db)):
    if not any(d.day_index == body.day_index for d in trip.days):
        raise HTTPException(422, "Day is outside the trip")
    if not any(c.place_id == body.place_id for c in trip.candidates):
        raise HTTPException(422, "Place is not in the trip's candidates")
    trip.constraints[:] = [
        c for c in trip.constraints if not (c.kind == "pin_day" and c.value.get("place_id") == body.place_id)
    ]
    trip.constraints.append(m.TripConstraint(kind="pin_day", value=body.model_dump()))
    db.commit()
    return [PinIn(**c.value) for c in trip.constraints if c.kind == "pin_day"]


@router.delete("/{trip_id}/pins/{place_id}", status_code=204)
def clear_pin(place_id: int, trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db)):
    trip.constraints[:] = [
        c for c in trip.constraints if not (c.kind == "pin_day" and c.value.get("place_id") == place_id)
    ]
    db.commit()
    return Response(status_code=204)


# ---- optimization
@router.post("/{trip_id}/optimize")
def optimize_trip(
    body: OptimizeIn,
    trip: m.Trip = Depends(owned_trip),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
):
    try:
        out, run = planning.run_optimization(
            db,
            trip,
            settings,
            body.solver,
            body.replace_manual,
            body.confirm_replace_manual,
            body.interest_weight,
            body.balance_weight,
            body.preview,
        )
    except planning.ManualEditsConflict as exc:
        raise HTTPException(
            409,
            {
                "message": "Replacing manual edits needs explicit confirmation (confirm_replace_manual=true).",
                "manual_stops": exc.names,
            },
        ) from exc
    return {
        "result": out,
        "run_id": run.id if run else None,
        "persisted": run is not None,
        "trip": None if run is None else trip_out(db, _load(db, trip.id)),
    }


@router.post("/{trip_id}/reschedule", response_model=TripOut)
def reschedule(
    trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)
):
    planning.retime(db, trip, settings)
    return trip_out(db, _load(db, trip.id))


@router.get("/{trip_id}/runs")
def list_runs(trip: m.Trip = Depends(owned_trip)):
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "created_at": r.created_at.isoformat(),
            "status": r.status,
            "solver": r.solver,
            "matrix_kind": r.matrix_kind,
            "input_hash": r.input_hash,
        }
        for r in reversed(trip.runs)
    ]


@router.get("/{trip_id}/runs/{run_id}")
def get_run(run_id: int, trip: m.Trip = Depends(owned_trip)):
    run = next((r for r in trip.runs if r.id == run_id), None)
    if run is None:
        raise HTTPException(404, "Run not found")
    return {
        "id": run.id,
        "kind": run.kind,
        "params": run.params,
        "input_hash": run.input_hash,
        "input_snapshot": run.input_snapshot,
        "result": run.result,
    }


@router.post("/{trip_id}/runs/{run_id}/reproduce")
def reproduce_run(run_id: int, trip: m.Trip = Depends(owned_trip)):
    run = next((r for r in trip.runs if r.id == run_id and r.kind == "optimize"), None)
    if run is None:
        raise HTTPException(404, "Run not found")
    again = planning.reproduce(run)
    same = [d["stops"] for d in again["days"]] == [d["stops"] for d in run.result["days"]]
    return {"identical_schedule": same, "result": again}


# ---- stop editing
def _stop(trip: m.Trip, stop_id: int) -> m.Stop:
    for d in trip.days:
        for s in d.stops:
            if s.id == stop_id:
                return s
    raise HTTPException(404, "Stop not found")


@router.post("/{trip_id}/stops", response_model=TripOut, status_code=201)
def create_stop(
    body: StopCreate,
    trip: m.Trip = Depends(owned_trip),
    user: m.User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
):
    place = planning.get_place_for_user(db, user.id, body.place_id)
    if place is None:
        raise HTTPException(404, "Place not found")
    if place.destination_id != trip.destination_id:
        raise HTTPException(422, "Place belongs to a different destination than the trip")
    try:
        planning.add_stop(db, trip, place, body.day_index, body.position, body.visit_minutes, body.notes)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    planning.retime(db, trip, settings)
    return trip_out(db, _load(db, trip.id))


@router.patch("/{trip_id}/stops/{stop_id}", response_model=TripOut)
def patch_stop(
    stop_id: int,
    body: StopPatch,
    trip: m.Trip = Depends(owned_trip),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
):
    stop = _stop(trip, stop_id)
    fields = body.model_fields_set
    try:
        if "day_index" in fields or "position" in fields:
            planning.move_stop(db, trip, stop, body.day_index, body.position)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.visit_minutes:
        stop.visit_minutes = body.visit_minutes
        for tp in trip.candidates:
            if tp.place_id == stop.place_id:
                tp.visit_minutes = body.visit_minutes
    if "notes" in fields:
        stop.notes = body.notes
    if body.locked is not None:
        stop.locked = body.locked
        if not body.locked:
            stop.origin = "optimized"
    db.commit()
    planning.retime(db, trip, settings)
    return trip_out(db, _load(db, trip.id))


@router.delete("/{trip_id}/stops/{stop_id}", response_model=TripOut)
def delete_stop(
    stop_id: int,
    forget: bool = False,
    trip: m.Trip = Depends(owned_trip),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
):
    stop = _stop(trip, stop_id)
    planning.remove_stop(db, trip, stop, forget)
    db.commit()
    planning.retime(db, trip, settings)
    return trip_out(db, _load(db, trip.id))
