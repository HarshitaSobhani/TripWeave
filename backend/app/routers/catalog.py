from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .. import models as m
from ..config import Settings, get_settings
from ..db import get_db
from ..deps import current_user
from ..schemas import DestinationOut, PlaceIn, PlaceOut
from ..services.planning import visible_place_filter

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/config")
def public_config(s: Settings = Depends(get_settings)):
    return {
        "routing_provider": s.routing_provider if s.routing_provider != "osrm" or s.osrm_base_url else "none",
        "fx_provider": s.fx_provider,
        "tile_url": s.map_tile_url,
        "tile_attribution": s.map_tile_attribution,
    }


@router.get("/destinations", response_model=list[DestinationOut])
def destinations(db: Session = Depends(get_db)):
    return db.scalars(select(m.Destination).order_by(m.Destination.name)).all()


@router.get("/places", response_model=list[PlaceOut])
def places(
    destination_id: int | None = None,
    q: str | None = Query(default=None, max_length=100),
    category: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    user: m.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = select(m.Place).options(joinedload(m.Place.source)).where(visible_place_filter(user.id))
    if destination_id:
        stmt = stmt.where(m.Place.destination_id == destination_id)
    if category:
        stmt = stmt.where(m.Place.category == category)
    if q:
        like = f"%{q.lower().replace('%', '').replace('_', '')}%"
        stmt = stmt.where(m.Place.name.ilike(like))
    return db.scalars(stmt.order_by(m.Place.name).limit(limit)).unique().all()


@router.post("/places", response_model=PlaceOut, status_code=201)
def create_place(body: PlaceIn, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    """User-defined place: private to its owner; provenance is the user."""
    if db.get(m.Destination, body.destination_id) is None:
        raise HTTPException(404, "Destination not found")
    now = datetime.now(UTC)
    place = m.Place(
        **body.model_dump(),
        owner_id=user.id,
        cost_recorded_at=now if body.cost is not None else None,
        opening_hours_verified_at=now if body.opening_hours is not None else None,
    )
    db.add(place)
    db.commit()
    db.refresh(place)
    return place
