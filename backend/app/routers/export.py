import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import models as m
from ..deps import owned_trip
from ..optimizer.hours import fmt_hhmm

router = APIRouter(prefix="/api/trips/{trip_id}", tags=["export"])

CSV_COLS = [
    "day",
    "date",
    "order",
    "start",
    "end",
    "place",
    "category",
    "lat",
    "lon",
    "visit_minutes",
    "leg_minutes",
    "leg_basis",
    "leg_distance_m",
    "leg_distance_kind",
    "origin",
    "locked",
    "notes",
    "warnings",
]


def _t(v: int | None) -> str:
    return "" if v is None else fmt_hhmm(v)


def rows(trip: m.Trip) -> list[dict]:
    out = []
    for d in trip.days:
        for s in sorted(d.stops, key=lambda s: s.position):
            out.append(
                {
                    "day": d.day_index + 1,
                    "date": d.date.isoformat(),
                    "order": s.position + 1,
                    "start": _t(s.start_min),
                    "end": _t(s.end_min),
                    "place": s.place.name,
                    "category": s.place.category,
                    "lat": s.place.lat,
                    "lon": s.place.lon,
                    "visit_minutes": s.visit_minutes,
                    "leg_minutes": s.leg_minutes if s.leg_minutes is not None else "",
                    "leg_basis": s.leg_basis or "",
                    "leg_distance_m": s.leg_distance_m if s.leg_distance_m is not None else "",
                    "leg_distance_kind": s.leg_distance_kind or "",
                    "origin": s.origin,
                    "locked": s.locked,
                    "notes": s.notes or "",
                    "warnings": "; ".join(s.warnings or []),
                }
            )
    return out


def _csv_safe(v):
    # neutralise spreadsheet formula injection
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def to_csv(trip: m.Trip) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLS, lineterminator="\n")
    w.writeheader()
    for r in rows(trip):
        w.writerow({k: _csv_safe(v) for k, v in r.items()})
    return buf.getvalue()


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(trip: m.Trip) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TripWeave//EN", "CALSCALE:GREGORIAN"]
    for d in trip.days:
        for s in sorted(d.stops, key=lambda s: s.position):
            if s.start_min is None or s.end_min is None:
                continue  # unscheduled stops have no honest time
            day = d.date.strftime("%Y%m%d")
            lines += [
                "BEGIN:VEVENT",
                f"UID:tripweave-{trip.id}-{s.id}@tripweave",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{day}T{s.start_min // 60:02d}{s.start_min % 60:02d}00",
                f"DTEND:{day}T{s.end_min // 60:02d}{s.end_min % 60:02d}00",
                f"SUMMARY:{_esc(s.place.name)}",
                f"GEO:{s.place.lat};{s.place.lon}",
            ]
            if s.notes:
                lines.append(f"DESCRIPTION:{_esc(s.notes)}")
            lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"  # times are floating (destination-local)


def to_json(trip: m.Trip) -> dict:
    return {
        "format": "tripweave-export",
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "trip": {
            "id": trip.id,
            "name": trip.name,
            "destination": trip.destination.name,
            "start_date": trip.start_date.isoformat(),
            "end_date": trip.end_date.isoformat(),
            "travelers": trip.travelers,
            "currency": trip.currency,
            "budget": str(trip.budget) if trip.budget is not None else None,
            "travel_mode": trip.travel_mode,
        },
        "notes": [
            "Times are destination-local, floating.",
            "leg_distance_kind 'straight_line_estimate' means a great-circle estimate, not a route or travel time.",
        ],
        "itinerary": rows(trip),
        "expenses": [
            {"category": e.category, "description": e.description, "amount": str(e.amount), "currency": e.currency}
            for e in trip.expenses
        ],
    }


@router.get("/export")
def export_trip(format: str = Query("json", pattern="^(json|csv|ics)$"), trip: m.Trip = Depends(owned_trip)):
    if format == "json":
        body, media = json.dumps(to_json(trip), indent=2, ensure_ascii=False), "application/json"
    elif format == "csv":
        body, media = to_csv(trip), "text/csv"
    elif format == "ics":
        body, media = to_ics(trip), "text/calendar"
    else:  # pragma: no cover
        raise HTTPException(400, "Unsupported format")
    return Response(
        body, media_type=media, headers={"Content-Disposition": f'attachment; filename="tripweave-{trip.id}.{format}"'}
    )
