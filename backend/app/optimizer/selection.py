"""Stage 1: place selection (dedupe, budget, rough capacity)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .domain import Candidate, Issue, ProblemSpec, Unscheduled
from .schedule import allowed_days


@dataclass
class Selection:
    selected: list[Candidate]
    deferred: list[Unscheduled] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    spend: Decimal = Decimal("0")


def is_forced(c: Candidate) -> bool:
    return c.mandatory or c.locked_day is not None


def stop_cost(spec: ProblemSpec, c: Candidate) -> Decimal | None:
    """Group cost in the trip currency, or None when unknown / not comparable."""
    if c.cost is None or c.cost_currency is None:
        return None
    if c.cost_currency != spec.currency:
        return None
    return c.cost * spec.travelers


def day_capacity(spec: ProblemSpec) -> int:
    total = 0
    for d in spec.days:
        span = d.end - d.start
        total += min(span, spec.max_daily_minutes) if spec.max_daily_minutes else span
    return total


def dedupe(cands: list[Candidate]) -> tuple[list[Candidate], list[Unscheduled]]:
    seen_keys: set[int] = set()
    seen_sig: dict[tuple[str, float, float], int] = {}
    out: list[Candidate] = []
    dropped: list[Unscheduled] = []
    for c in sorted(cands, key=lambda x: (not is_forced(x), x.key)):
        sig = (c.name.strip().lower(), round(c.lat, 5), round(c.lon, 5))
        if c.key in seen_keys:
            dropped.append(Unscheduled(c.key, "duplicate", "Same place listed more than once."))
            continue
        if sig in seen_sig:
            dropped.append(
                Unscheduled(c.key, "duplicate", f"Duplicate of place {seen_sig[sig]} (same name and location).")
            )
            continue
        seen_keys.add(c.key)
        seen_sig[sig] = c.key
        out.append(c)
    return out, dropped


def select_places(spec: ProblemSpec) -> Selection:
    cands, dropped = dedupe(spec.candidates)
    sel = Selection(selected=[], deferred=list(dropped))
    forced = sorted((c for c in cands if is_forced(c)), key=lambda c: c.key)
    optional = sorted(
        (c for c in cands if not is_forced(c)),
        key=lambda c: (-c.interest, -(c.interest / max(c.visit_minutes, 1)), c.key),
    )
    spend = spec.committed_spend
    unknown = 0
    other_ccy = 0
    for c in forced:
        sel.selected.append(c)
        cost = stop_cost(spec, c)
        if cost is not None:
            spend += cost
    capacity = day_capacity(spec)
    used = sum(c.visit_minutes for c in forced if allowed_days(c, spec.days))
    for c in optional:
        cost = stop_cost(spec, c)
        if cost is None and c.cost is not None:
            other_ccy += 1
        elif cost is None:
            unknown += 1
        if spec.budget is not None and cost is not None and spend + cost > spec.budget:
            sel.deferred.append(Unscheduled(c.key, "budget", f"Adding {cost} {spec.currency} would exceed the budget."))
            continue
        if used + c.visit_minutes > capacity:
            sel.deferred.append(Unscheduled(c.key, "capacity", "Not enough daily time left for this visit."))
            continue
        sel.selected.append(c)
        used += c.visit_minutes
        if cost is not None:
            spend += cost
    sel.spend = spend
    if spec.budget is not None and spend > spec.budget:
        sel.issues.append(
            Issue(
                "error",
                "budget_exceeded",
                f"Mandatory/locked stops and expenses cost {spend} {spec.currency}, above the {spec.budget} budget.",
            )
        )
    if spec.budget is not None and unknown:
        sel.issues.append(
            Issue(
                "warning",
                "cost_unknown",
                f"{unknown} optional place(s) have no recorded cost; budget check ignores them.",
            )
        )
    if other_ccy:
        sel.issues.append(
            Issue(
                "warning",
                "currency_mismatch",
                f"{other_ccy} place(s) are priced in another currency and are not counted against the {spec.currency} budget (no FX conversion configured).",
            )
        )
    return sel
