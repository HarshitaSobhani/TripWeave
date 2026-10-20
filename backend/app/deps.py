from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import models as m
from .config import Settings, get_settings
from .db import get_db
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> m.User:
    uid = decode_token(cred.credentials) if cred else None
    user = db.get(m.User, uid) if uid else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    return user


def owned_trip(trip_id: int, user: m.User = Depends(current_user), db: Session = Depends(get_db)) -> m.Trip:
    """Private trips: anyone but the owner gets 404 (existence is not revealed)."""
    trip = db.scalar(
        select(m.Trip)
        .where(m.Trip.id == trip_id, m.Trip.owner_id == user.id)
        .options(
            selectinload(m.Trip.days).selectinload(m.TripDay.stops).selectinload(m.Stop.place),
        )
    )
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    return trip


def settings_dep() -> Settings:
    return get_settings()
