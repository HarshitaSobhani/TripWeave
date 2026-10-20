from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import models as m
from ..config import Settings
from ..db import get_db
from ..deps import owned_trip, settings_dep
from ..fx import FxError, fetch_rate
from ..money import q, totals_by_currency
from ..schemas import ExpenseIn, ExpenseOut

router = APIRouter(prefix="/api/trips/{trip_id}", tags=["budget"])


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(trip: m.Trip = Depends(owned_trip)):
    return trip.expenses


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def add_expense(body: ExpenseIn, trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db)):
    if body.day_index is not None and not any(d.day_index == body.day_index for d in trip.days):
        raise HTTPException(422, "Day is outside the trip")
    e = m.Expense(**body.model_dump())
    trip.expenses.append(e)
    db.commit()
    return e


@router.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, body: ExpenseIn, trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db)):
    e = next((x for x in trip.expenses if x.id == expense_id), None)
    if e is None:
        raise HTTPException(404, "Expense not found")
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    db.commit()
    return e


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, trip: m.Trip = Depends(owned_trip), db: Session = Depends(get_db)):
    e = next((x for x in trip.expenses if x.id == expense_id), None)
    if e is None:
        raise HTTPException(404, "Expense not found")
    trip.expenses.remove(e)
    db.commit()
    return Response(status_code=204)


def budget_summary(trip: m.Trip, settings: Settings, client=None) -> dict:
    admission: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    unknown = 0
    for d in trip.days:
        for s in d.stops:
            p = s.place
            if p.cost is None or p.cost_currency is None:
                unknown += 1
            else:
                admission[p.cost_currency] += p.cost * trip.travelers
    by_cat: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    for e in trip.expenses:
        by_cat[e.category][e.currency] += e.amount
    totals = totals_by_currency(
        [(c, a) for c, a in admission.items()] + [(e.currency, e.amount) for e in trip.expenses]
    )
    out: dict = {
        "currency": trip.currency,
        "travelers": trip.travelers,
        "planned_admission": {c: str(q(a)) for c, a in sorted(admission.items())},
        "stops_without_known_cost": unknown,
        "expenses_by_category": {k: {c: str(q(a)) for c, a in sorted(v.items())} for k, v in sorted(by_cat.items())},
        "totals_by_currency": {c: str(a) for c, a in totals.items()},
        "budget": str(trip.budget) if trip.budget is not None else None,
        "in_trip_currency": str(totals.get(trip.currency, Decimal("0.00"))),
        "remaining_in_trip_currency": None,
        "over_budget": None,
        "conversion": {"provider": settings.fx_provider, "converted_total": None, "rates": [], "note": None},
        "notes": ["Admission is derived from recorded place costs x travellers; do not also enter it as an expense."],
    }
    in_ccy = totals.get(trip.currency, Decimal("0"))
    other = {c: a for c, a in totals.items() if c != trip.currency}
    conv_total: Decimal | None = in_ccy
    if other:
        if settings.fx_provider == "none":
            out["conversion"]["note"] = (
                "Amounts in other currencies are listed separately; no conversion provider is configured."
            )
            conv_total = None
        else:
            try:
                for ccy, amt in other.items():
                    r = fetch_rate(settings, ccy, trip.currency, client)
                    conv_total = conv_total + amt * r.rate if conv_total is not None else None
                    out["conversion"]["rates"].append(
                        {
                            "from": ccy,
                            "to": trip.currency,
                            "rate": str(r.rate),
                            "as_of": r.as_of,
                            "provider": r.provider,
                        }
                    )
            except FxError as exc:
                conv_total = None
                out["conversion"]["note"] = f"Conversion unavailable: {exc}"
    if conv_total is not None:
        out["conversion"]["converted_total"] = str(q(conv_total))
        if trip.budget is not None:
            out["remaining_in_trip_currency"] = str(q(trip.budget - conv_total))
            out["over_budget"] = conv_total > trip.budget
    return out


@router.get("/budget")
def get_budget(trip: m.Trip = Depends(owned_trip), settings: Settings = Depends(settings_dep)):
    return budget_summary(trip, settings)
