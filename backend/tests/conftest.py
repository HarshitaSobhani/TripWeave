import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.db import Base, get_db, make_engine
from app.main import app
from app.seed.__main__ import seed


@pytest.fixture()
def engine():
    # TEST_DATABASE_URL (e.g. a throwaway PostgreSQL database) runs the suite on that backend.
    eng = make_engine(os.environ.get("TEST_DATABASE_URL", "sqlite://"))
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def Session(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(Session):
    with Session() as s:
        seed(s)
        yield s


@pytest.fixture()
def client(Session, db):
    def _get_db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, email="a@example.com", password="password123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def auth(client):
    return register(client)


@pytest.fixture()
def paris(client, auth):
    return next(d for d in client.get("/api/destinations").json() if d["name"] == "Paris")


@pytest.fixture()
def paris_places(client, auth, paris):
    ps = client.get("/api/places", params={"destination_id": paris["id"]}, headers=auth).json()
    return {p["name"]: p for p in ps}


def trip_payload(dest_id, **over):
    base = {
        "name": "Paris test",
        "destination_id": dest_id,
        "start_date": "2030-01-07",
        "end_date": "2030-01-08",
        "travelers": 2,
        "day_start": "09:00:00",
        "day_end": "18:00:00",
        "currency": "EUR",
        "budget": "500.00",
        "travel_mode": "walking",
        "transit_buffer_minutes": 15,
    }
    base.update(over)
    return base


@pytest.fixture()
def trip(client, auth, paris):
    r = client.post("/api/trips", json=trip_payload(paris["id"]), headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def add_candidates(client, auth, trip_id, places, **kw):
    for p in places:
        r = client.put(f"/api/trips/{trip_id}/candidates", json={"place_id": p["id"], **kw}, headers=auth)
        assert r.status_code == 200, r.text
