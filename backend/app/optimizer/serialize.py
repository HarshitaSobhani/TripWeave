"""JSON (de)serialization of problems and results for reproducible runs."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from .domain import (
    Candidate,
    DayPlan,
    OptimizationResult,
    Point,
    ProblemSpec,
    TravelMatrix,
)


def spec_to_json(spec: ProblemSpec) -> dict[str, Any]:
    return {
        "candidates": [
            {
                **{k: v for k, v in asdict(c).items() if k not in ("cost", "hours")},
                "cost": str(c.cost) if c.cost is not None else None,
                "hours": None if c.hours is None else {str(k): [list(w) for w in v] for k, v in c.hours.items()},
            }
            for c in sorted(spec.candidates, key=lambda c: c.key)
        ],
        "days": [{"index": d.index, "date": d.date.isoformat(), "start": d.start, "end": d.end} for d in spec.days],
        "travelers": spec.travelers,
        "budget": str(spec.budget) if spec.budget is not None else None,
        "currency": spec.currency,
        "committed_spend": str(spec.committed_spend),
        "max_daily_minutes": spec.max_daily_minutes,
        "max_travel_minutes": spec.max_travel_minutes,
        "max_leg_minutes": spec.max_leg_minutes,
        "transit_buffer_minutes": spec.transit_buffer_minutes,
        "start_point": asdict(spec.start_point) if spec.start_point else None,
        "end_point": asdict(spec.end_point) if spec.end_point else None,
        "interest_weight": spec.interest_weight,
        "balance_weight": spec.balance_weight,
        "mode": spec.mode,
    }


def spec_from_json(data: dict[str, Any]) -> ProblemSpec:
    cands = []
    for c in data["candidates"]:
        c = dict(c)
        c["cost"] = Decimal(c["cost"]) if c["cost"] is not None else None
        h = c["hours"]
        c["hours"] = None if h is None else {int(k): [tuple(w) for w in v] for k, v in h.items()}
        cands.append(Candidate(**c))
    return ProblemSpec(
        candidates=cands,
        days=[DayPlan(d["index"], date.fromisoformat(d["date"]), d["start"], d["end"]) for d in data["days"]],
        travelers=data["travelers"],
        budget=Decimal(data["budget"]) if data["budget"] is not None else None,
        currency=data["currency"],
        committed_spend=Decimal(data["committed_spend"]),
        max_daily_minutes=data["max_daily_minutes"],
        max_travel_minutes=data["max_travel_minutes"],
        max_leg_minutes=data.get("max_leg_minutes"),
        transit_buffer_minutes=data["transit_buffer_minutes"],
        start_point=Point(**data["start_point"]) if data["start_point"] else None,
        end_point=Point(**data["end_point"]) if data["end_point"] else None,
        interest_weight=data["interest_weight"],
        balance_weight=data["balance_weight"],
        mode=data["mode"],
    )


def matrix_to_json(m: TravelMatrix) -> dict[str, Any]:
    return {
        "keys": m.keys,
        "kind": m.kind,
        "distances_m": m.distances_m,
        "durations_s": m.durations_s,
        "provider": m.provider,
        "mode": m.mode,
        "fetched_at": m.fetched_at,
        "notes": m.notes,
    }


def matrix_from_json(d: dict[str, Any]) -> TravelMatrix:
    return TravelMatrix(
        keys=d["keys"],
        kind=d["kind"],
        distances_m=d["distances_m"],
        durations_s=d["durations_s"],
        provider=d["provider"],
        mode=d["mode"],
        fetched_at=d.get("fetched_at"),
        notes=d.get("notes", []),
    )


def result_to_json(res: OptimizationResult) -> dict[str, Any]:
    return {
        "status": res.status,
        "solver": res.solver,
        "days": [
            {
                "day_index": d.day_index,
                "date": d.date.isoformat(),
                "visit_minutes": d.visit_minutes,
                "travel_minutes": d.travel_minutes,
                "wait_minutes": d.wait_minutes,
                "distance_m": d.distance_m,
                "distance_kind": d.distance_kind,
                "day_end_used": d.day_end_used,
                "stops": [asdict(s) for s in d.stops],
            }
            for d in res.days
        ],
        "unscheduled": [asdict(u) for u in res.unscheduled],
        "issues": [i.as_dict() for i in res.issues],
        "explanation": res.explanation,
        "metrics": res.metrics,
        "matrix_kind": res.matrix_kind,
        "matrix_provider": res.matrix_provider,
        "params": res.params,
    }
