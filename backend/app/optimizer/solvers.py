"""Stage 4: optimization. OR-Tools VRP with a deterministic heuristic fallback."""

from __future__ import annotations

import itertools

from ortools.util.optional_boolean_pb2 import BOOL_TRUE

from .domain import Candidate, ProblemSpec
from .schedule import allowed_days, day_cost, pkey, simulate_day, valid_start_ranges
from .selection import is_forced
from .travel import TravelModel

BIG_PENALTY = 1_000_000
SCALE_TIME_LIMIT_S = 10


class SolverUnavailable(RuntimeError):
    pass


def default_interest_weight(tm: TravelModel) -> float:
    # Cost units one interest point is worth. Routed: travel-minutes; straight-line: metres.
    # Deliberately generous so selected places are kept whenever they fit; the weight
    # decides which stops lose out when time or workload is scarce.
    return 240.0 if tm.routed else 5000.0


def default_balance_weight(tm: TravelModel) -> float:
    return 1.0 if tm.routed else 20.0


def solve_ortools(spec: ProblemSpec, cands: list[Candidate], tm: TravelModel) -> dict[int, list[int]]:
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except Exception as exc:  # pragma: no cover - import guard
        raise SolverUnavailable(f"OR-Tools unavailable: {exc}") from exc

    iw = spec.interest_weight if spec.interest_weight is not None else default_interest_weight(tm)
    bw = spec.balance_weight if spec.balance_weight is not None else default_balance_weight(tm)
    days = spec.days
    V = len(days)
    cands = sorted(cands, key=lambda c: c.key)

    # node layout: 0 = start depot, 1 = end depot, then one copy per (place, allowed day)
    nodes: list[tuple[str | None, Candidate | None, int | None]] = [
        ("start" if spec.start_point else None, None, None),
        ("end" if spec.end_point else None, None, None),
    ]
    copies: dict[int, list[int]] = {}
    for c in cands:
        for d in allowed_days(c, days):
            copies.setdefault(c.key, []).append(len(nodes))
            nodes.append((pkey(c.key), c, d.index))
    N = len(nodes)
    if N == 2:
        return {d.index: [] for d in days}

    def travel_min(a: int, b: int) -> int:
        ka, kb = nodes[a][0], nodes[b][0]
        if ka is None or kb is None:
            return 0
        return tm.minutes(ka, kb)

    def arc_cost(a: int, b: int) -> int:
        ka, kb = nodes[a][0], nodes[b][0]
        if ka is None or kb is None:
            return 0
        return tm.cost(ka, kb)

    tmin = [[travel_min(a, b) for b in range(N)] for a in range(N)]
    cost = [[arc_cost(a, b) for b in range(N)] for a in range(N)]
    service = [(nd.visit_minutes if (nd := nodes[a][1]) else 0) for a in range(N)]

    manager = pywrapcp.RoutingIndexManager(N, V, [0] * V, [1] * V)
    routing = pywrapcp.RoutingModel(manager)

    cost_cb = routing.RegisterTransitCallback(lambda i, j: cost[manager.IndexToNode(i)][manager.IndexToNode(j)])
    routing.SetArcCostEvaluatorOfAllVehicles(cost_cb)

    def work_fn(i: int, j: int) -> int:
        a, b = manager.IndexToNode(i), manager.IndexToNode(j)
        return service[a] + tmin[a][b]

    work_cb = routing.RegisterTransitCallback(work_fn)
    routing.AddDimension(work_cb, 1440, 1440, False, "Time")
    time = routing.GetDimensionOrDie("Time")

    cap = [min(d.end - d.start, spec.max_daily_minutes) if spec.max_daily_minutes else d.end - d.start for d in days]
    routing.AddDimensionWithVehicleCapacity(work_cb, 0, cap, True, "Work")
    work = routing.GetDimensionOrDie("Work")

    if tm.routed and spec.max_travel_minutes is not None:
        tr_cb = routing.RegisterTransitCallback(lambda i, j: tmin[manager.IndexToNode(i)][manager.IndexToNode(j)])
        routing.AddDimension(tr_cb, 0, spec.max_travel_minutes, True, "Travel")

    for v, d in enumerate(days):
        time.CumulVar(routing.Start(v)).SetRange(d.start, d.start)
        time.CumulVar(routing.End(v)).SetRange(d.start, d.end)

    for n in range(2, N):
        _, node_c, di = nodes[n]
        assert node_c is not None and di is not None
        c = node_c
        idx = manager.NodeToIndex(n)
        ranges = valid_start_ranges(c, days[di])
        time.CumulVar(idx).SetRange(ranges[0][0], ranges[-1][1])
        for (_, hi), (lo, _) in itertools.pairwise(ranges):
            time.CumulVar(idx).RemoveInterval(hi + 1, lo - 1)
        # SetAllowedVehiclesForIndex has a broken Span binding in some OR-Tools wheels
        vehicle_var = routing.VehicleVar(idx)
        for other in range(V):
            if other != di:
                vehicle_var.RemoveValue(other)

    for c in cands:
        idxs = [manager.NodeToIndex(n) for n in copies.get(c.key, [])]
        if not idxs:
            continue
        penalty = BIG_PENALTY if is_forced(c) else int(iw * c.interest)
        routing.AddDisjunction(idxs, penalty, 1)

    if bw > 0 and V > 1:
        # Spread load: penalise each day's workload above the even share. (The global
        # span coefficient ignores unused vehicles, so it would not spread anything.)
        total_visit = sum(c.visit_minutes for c in cands)
        target = -(-total_visit // V)
        for v in range(V):
            work.SetCumulVarSoftUpperBound(routing.End(v), target, int(bw))

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GREEDY_DESCENT
    ops = params.local_search_operators
    # Day copies of a place are alternatives in one disjunction: moving a stop between
    # days is a swap of active nodes, so these operators must be on.
    ops.use_make_active = BOOL_TRUE
    ops.use_swap_active = BOOL_TRUE
    ops.use_extended_swap_active = BOOL_TRUE
    ops.use_make_inactive = BOOL_TRUE
    params.time_limit.seconds = SCALE_TIME_LIMIT_S
    solution = routing.SolveWithParameters(params)
    if solution is None:
        raise SolverUnavailable("OR-Tools found no feasible solution")

    out: dict[int, list[int]] = {}
    for v, d in enumerate(days):
        seq: list[int] = []
        idx = solution.Value(routing.NextVar(routing.Start(v)))
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            cand = nodes[node][1]
            assert cand is not None
            seq.append(cand.key)
            idx = solution.Value(routing.NextVar(idx))
        out[d.index] = seq
    return out


def _two_opt(spec: ProblemSpec, tm: TravelModel, day, seq: list[int], cmap: dict[int, Candidate]) -> list[int]:
    best = list(seq)
    best_cost = day_cost(spec, tm, best)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                trial = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                c = day_cost(spec, tm, trial)
                if c < best_cost and simulate_day(spec, tm, day, trial, cmap).ok:
                    best, best_cost, improved = trial, c, True
    return best


def solve_fallback(spec: ProblemSpec, cands: list[Candidate], tm: TravelModel) -> dict[int, list[int]]:
    """Cheapest feasible insertion + 2-opt. Deterministic; not globally optimal."""
    bw = spec.balance_weight if spec.balance_weight is not None else default_balance_weight(tm)
    cmap = {c.key: c for c in cands}
    seqs: dict[int, list[int]] = {d.index: [] for d in spec.days}
    order = sorted(cands, key=lambda c: (not is_forced(c), -c.interest, c.visit_minutes, c.key))
    for c in order:
        best: tuple[float, int, int] | None = None
        for d in allowed_days(c, spec.days):
            base = seqs[d.index]
            base_cost = day_cost(spec, tm, base)
            for pos in range(len(base) + 1):
                trial = [*base[:pos], c.key, *base[pos:]]
                sim = simulate_day(spec, tm, d, trial, cmap)
                if not sim.ok:
                    continue
                score = day_cost(spec, tm, trial) - base_cost + bw * sim.work_minutes
                cand_key = (score, d.index, pos)
                if best is None or cand_key < best:
                    best = cand_key
        if best is not None:
            _, di, pos = best
            seqs[di].insert(pos, c.key)
    for d in spec.days:
        if len(seqs[d.index]) > 2:
            seqs[d.index] = _two_opt(spec, tm, d, seqs[d.index], cmap)
    return seqs
