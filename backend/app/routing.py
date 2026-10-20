"""Routing adapters. Real routes only come from a configured provider.

Never presents straight-line distance as a route or a travel time: when no
provider is configured (or it fails / returns invalid data) the matrix is
labelled `straight_line_estimate` and carries no durations.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .optimizer.domain import TravelMatrix
from .optimizer.geo import haversine_m

OSRM_PROFILES = {"driving": "driving", "walking": "foot", "cycling": "bike", "transit": "driving"}


class RoutingError(Exception):
    pass


Points = list[tuple[str, float, float]]


def straight_line_matrix(points: Points, mode: str, notes: list[str] | None = None) -> TravelMatrix:
    dist: list[list[float | None]] = [
        [0.0 if i == j else round(haversine_m(a[1], a[2], b[1], b[2]), 1) for j, b in enumerate(points)]
        for i, a in enumerate(points)
    ]
    return TravelMatrix(
        keys=[p[0] for p in points],
        kind="straight_line_estimate",
        distances_m=dist,
        durations_s=None,
        provider="straight_line",
        mode=mode,
        fetched_at=datetime.now(UTC).isoformat(),
        notes=notes or [],
    )


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise RoutingError(f"invalid number in routing response: {v!r}")
    return float(v)


def _grid(raw: Any, n: int, name: str) -> list[list[float | None]]:
    if not isinstance(raw, list) or len(raw) != n:
        raise RoutingError(f"routing response '{name}' has wrong shape")
    out = []
    for row in raw:
        if not isinstance(row, list) or len(row) != n:
            raise RoutingError(f"routing response '{name}' has wrong shape")
        out.append([_num(v) for v in row])
    return out


def parse_osrm_table(payload: Any, points: Points, mode: str, provider: str) -> TravelMatrix:
    """Validate an OSRM /table response. Raises RoutingError on anything unexpected."""
    if not isinstance(payload, dict) or payload.get("code") != "Ok":
        raise RoutingError(
            f"routing service returned {payload.get('code') if isinstance(payload, dict) else 'non-object'}"
        )
    n = len(points)
    dur = _grid(payload.get("durations"), n, "durations")
    dist = _grid(payload.get("distances"), n, "distances")
    for i in range(n):
        dur[i][i] = 0.0
        dist[i][i] = 0.0
    return TravelMatrix(
        keys=[p[0] for p in points],
        kind="routed",
        distances_m=dist,
        durations_s=dur,
        provider=provider,
        mode=mode,
        fetched_at=datetime.now(UTC).isoformat(),
    )


def osrm_matrix(settings: Settings, points: Points, mode: str, client: httpx.Client | None = None) -> TravelMatrix:
    if not settings.osrm_base_url:
        raise RoutingError("OSRM_BASE_URL is not configured")
    if len(points) > settings.routing_max_points:
        raise RoutingError(f"{len(points)} points exceed ROUTING_MAX_POINTS={settings.routing_max_points}")
    profile = OSRM_PROFILES.get(mode, "driving")
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for _, lat, lon in points)
    url = f"{settings.osrm_base_url.rstrip('/')}/table/v1/{quote(profile)}/{coords}"
    own = client is None
    client = client or httpx.Client(timeout=settings.routing_timeout_s)
    try:
        resp = client.get(url, params={"annotations": "duration,distance"})
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RoutingError(f"routing request failed: {exc}") from exc
    finally:
        if own:
            client.close()
    return parse_osrm_table(payload, points, mode, f"osrm:{settings.osrm_base_url}")


def acquire_matrix(settings: Settings, points: Points, mode: str, client: httpx.Client | None = None) -> TravelMatrix:
    """Configured provider with an honest fallback; never raises for provider failures."""
    if len(points) < 2:
        return straight_line_matrix(points, mode)
    if settings.routing_provider == "osrm":
        try:
            return osrm_matrix(settings, points, mode, client)
        except RoutingError as exc:
            return straight_line_matrix(
                points, mode, [f"Routing unavailable ({exc}); using straight-line estimates instead."]
            )
    return straight_line_matrix(points, mode)
