"""Idempotent: python -m app.seed"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import SessionLocal
from .data import DESTINATIONS, PLACES, SOURCE


def seed(db: Session) -> dict[str, int]:
    src = db.scalar(select(m.SourceMeta).where(m.SourceMeta.name == SOURCE["name"]))
    if src is None:
        src = m.SourceMeta(**SOURCE)
        db.add(src)
        db.flush()
    dests: dict[str, m.Destination] = {}  # keyed by name
    for d in DESTINATIONS:
        row = db.scalar(select(m.Destination).where(m.Destination.name == d["name"]))
        if row is None:
            row = m.Destination(**d, source_id=src.id)
            db.add(row)
            db.flush()
        dests[d["name"]] = row
    added = 0
    for dest, name, cat, lat, lon, desc in PLACES:
        exists = db.scalar(
            select(m.Place.id).where(
                m.Place.destination_id == dests[dest].id, m.Place.name == name, m.Place.owner_id.is_(None)
            )
        )
        if exists:
            continue
        db.add(
            m.Place(
                destination_id=dests[dest].id,
                name=name,
                category=cat,
                lat=lat,
                lon=lon,
                description=desc,
                source_id=src.id,
            )
        )
        added += 1
    db.commit()
    return {"destinations": len(dests), "places_added": added}


if __name__ == "__main__":
    with SessionLocal() as session:
        print(seed(session))
