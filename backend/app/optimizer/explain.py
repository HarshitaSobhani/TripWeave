"""Stage 7: human-readable explanation of what shaped the plan."""

from __future__ import annotations

from .domain import Candidate, OptimizationResult, ProblemSpec
from .hours import fmt_hhmm
from .travel import TravelModel


def explain(spec: ProblemSpec, tm: TravelModel, res: OptimizationResult, cmap: dict[int, Candidate]) -> list[str]:
    out: list[str] = []
    if tm.routed:
        out.append(
            f"Stops were ordered to minimise real travel time from '{res.matrix_provider}' "
            f"({spec.mode}); each optional stop was weighed at {res.params['interest_weight']:g} "
            "travel-minutes per interest point."
        )
    else:
        out.append(
            "No routing data was available. Stops were ordered to reduce straight-line distance, "
            "which is only an ordering proxy. Real walking or driving time may differ substantially."
        )
    out.append(f"Solver: {res.solver}.")
    for d in res.days:
        if not d.stops:
            out.append(f"Day {d.day_index + 1}: no stops.")
            continue
        names = " -> ".join(cmap[s.key].name for s in d.stops)
        out.append(f"Day {d.day_index + 1}: {names}.")
        for s in d.stops:
            c = cmap[s.key]
            if s.wait > 0:
                out.append(f"'{c.name}' waits {s.wait} min for opening at {fmt_hhmm(s.start)}.")
            if c.locked_day is not None:
                out.append(f"'{c.name}' kept on day {c.locked_day + 1} because you placed it manually.")
            elif c.pinned_day is not None:
                out.append(f"'{c.name}' placed on day {c.pinned_day + 1} by your pin constraint.")
            elif c.mandatory:
                out.append(f"'{c.name}' is mandatory and was prioritised.")
    for u in res.unscheduled:
        out.append(f"Not scheduled: '{cmap[u.key].name}' ({u.code}): {u.detail}")
    if spec.max_daily_minutes:
        out.append(f"Daily workload (visits + travel) capped at {spec.max_daily_minutes} min.")
    return out
