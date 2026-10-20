import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import auth, budget, catalog, export, trips

_log = logging.getLogger("tripweave")
if get_settings().secret_key.startswith("dev-only"):
    _log.warning("SECRET_KEY is the development default; set a long random value before deploying.")

app = FastAPI(
    title="TripWeave API",
    version="1.0.0",
    description="Constraint-aware travel itinerary planner. See docs/optimization.md.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (auth.router, catalog.router, trips.router, budget.router, export.router):
    app.include_router(r)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}
