"""Run the optimizer standalone (no database, no network).

    cd backend && python -m examples.optimize_demo [--solver ortools|fallback] [--days N]

Uses the curated Paris landmarks. Without routing data it orders stops by
straight-line distance and says so; pass --osrm-url to use an OSRM server.
"""

import argparse
from datetime import date, timedelta

from app.config import Settings
from app.optimizer import Candidate, DayPlan, Point, ProblemSpec, optimize
from app.optimizer.hours import fmt_hhmm
from app.routing import acquire_matrix
from app.seed.data import PLACES


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solver", default="auto", choices=["auto", "ortools", "fallback"])
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--osrm-url", default="")
    args = ap.parse_args()

    paris = [p for p in PLACES if p[0] == "Paris"]
    cands = [
        Candidate(
            key=i,
            name=n,
            lat=la,
            lon=lo,
            visit_minutes=90,
            interest=4 if cat == "museum" else 3,
            mandatory=(n == "Eiffel Tower"),
            category=cat,
        )
        for i, (_, n, cat, la, lo, _) in enumerate(paris, 1)
    ]
    start = date(2030, 1, 7)
    spec = ProblemSpec(
        candidates=cands,
        days=[DayPlan(d, start + timedelta(days=d), 9 * 60, 18 * 60) for d in range(args.days)],
        start_point=Point(48.8566, 2.3522, "Hotel (example)"),
        end_point=Point(48.8566, 2.3522, "Hotel (example)"),
        max_daily_minutes=420,
    )
    settings = Settings(routing_provider="osrm" if args.osrm_url else "none", osrm_base_url=args.osrm_url)
    res = optimize(spec, lambda pts, mode: acquire_matrix(settings, pts, mode), args.solver)

    names = {c.key: c.name for c in cands}
    print(f"status={res.status} solver={res.solver} matrix={res.matrix_kind} ({res.matrix_provider})")
    for d in res.days:
        print(f"\nDay {d.day_index + 1} {d.date}: distance {d.distance_m:.0f} m ({d.distance_kind})")
        for s in d.stops:
            print(f"  {fmt_hhmm(s.start)}-{fmt_hhmm(s.end)}  {names[s.key]}")
    for u in res.unscheduled:
        print(f"unscheduled: {names[u.key]} [{u.code}] {u.detail}")
    for i in res.issues:
        print(f"{i.severity}: {i.message}")
    print()
    print("\n".join(res.explanation))


if __name__ == "__main__":
    main()
