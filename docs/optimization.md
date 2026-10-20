# Optimization architecture

Code: `backend/app/optimizer/` (pure Python, no DB access). DB glue: `backend/app/services/planning.py`.

## Pipeline (`pipeline.optimize`)

| # | Stage | Module | Output |
|---|---|---|---|
| 1 | Place selection | `selection.py` | Dedupes (same key or same name+location), keeps mandatory/locked stops, adds optional stops by interest until budget or total daily capacity is used. Deferred stops get reasons (`budget`, `capacity`, `duplicate`). |
| 2 | Matrix acquisition | `routing.py` (+ `MatrixFn` callback) | `TravelMatrix` labelled `routed` or `straight_line_estimate`. Called **after** selection, once. |
| 3 | Constraint validation | `validation.validate_spec` | Errors/warnings: bad coordinates, durations, pins outside the trip, places with no feasible day, mandatory time over capacity, budget exceeded by mandatory stops. |
| 4 | Optimization | `solvers.py` | Day -> ordered place keys. |
| 5 | Schedule construction | `schedule.py` | Times for every stop (arrive/start/end/wait), leg data, workload. Drops optional stops that overflow. |
| 6 | Result validation | `validation.validate_result` | Independent re-check: duplicates, overlaps, day window, opening hours, workload, mandatory accounted for. |
| 7 | Explanation | `explain.py` | Ordering rationale, waits, locked/pinned stops, unscheduled reasons. |

## Honesty rules

* `routed` matrix: durations/distances from the routing provider. Scheduled minutes = `ceil(duration/60)` plus your transit buffer.
* `straight_line_estimate` matrix: great-circle metres only, **no durations**. Used purely as an ordering cost.
  Scheduling uses your *transit buffer* (a user assumption, labelled `user_buffer`). `metrics.travel_minutes` is `null`.
* Every leg and metric carries its kind (`routed` / `straight_line_estimate`); UI wording is derived from it.
* Max travel per day and max single leg need real durations; without them a warning says they were not enforced.
* Unknown opening hours are assumed open and reported. Hours need a source (provenance). Costs in another currency than the trip's are never compared to the budget.
* Default visit duration (60 min) is applied only when neither place nor user gives one, and is reported.

## OR-Tools model (`solve_ortools`)

* One vehicle per day. Each place gets one node **per allowed day** (days where it is open and fits), joined by a
  disjunction (visit at most once, penalty if skipped). Exact per-day opening windows (multiple windows, lunch breaks) become node time windows.
* Dimensions: `Time` (visit + travel + waiting, window = day), `Work` (visit + travel, cap = max daily workload), optional `Travel` cap (routed only).
* Arc cost: routed minutes, or straight-line metres.
* Skip penalty: `interest x interest_weight` (defaults 240 travel-minutes per point routed, 5000 m per point straight-line, deliberately
  generous so that selected places are kept whenever they fit). Mandatory and locked stops carry a huge penalty (dropped only if truly infeasible, then reported).
* Load spreading: soft upper bound on each day's workload at the even share, weight `balance_weight`.
* Pins/locks restrict a place to one day's node. Locked stops are re-ordered afterwards to their manual relative order.
* Search: PATH_CHEAPEST_ARC first solution, greedy descent with `swap_active`/`make_active` operators enabled (needed for moving a stop between day copies), 10 s safety limit. No random seeds, inputs sorted by id.

**Determinism:** identical inputs and data give identical output (tested, including input order). Each stored run keeps
the spec and the matrix; `POST /api/trips/{id}/runs/{run}/reproduce` re-solves from the snapshot and reports whether the schedule is identical.

## Fallback optimizer (`solve_fallback`)

Used when OR-Tools is unavailable/finds nothing (`solver=auto`) or when chosen. Cheapest feasible insertion (forced stops, then interest
descending), then 2-opt per day, every candidate move checked against the same schedule simulator. **Limitations:** greedy; no global optimality;
interest only prioritises insertion order (it does not trade interest against travel); can be worse than OR-Tools (tested on a line dataset where both are optimal).

## Manual edits

* Moving/adding a stop marks it `manual` + `locked`; "Keep here" toggles the lock.
* Re-optimizing keeps locked stops on their day and relative order, and plans everything else around them.
* `replace_manual=true` without `confirm_replace_manual=true` returns **409** listing the stops; nothing changes. The UI shows a confirmation.
* Removed stops become `excluded` candidates and are not re-added.
* Locked stops that cannot be scheduled stay in the plan with a warning, never silently dropped.

## Limitations

* Straight-line mode cannot know real travel time; orderings can be poor in cities with rivers/rail barriers.
* Routing matrix is one request per optimization (default max 80 points); public OSRM demo servers only serve the car profile and are not for production.
* No live opening hours, availability, transit timetables or weather; no bounded optimality proof (solver time-limited, local search).
* Opening hours editor supports one window per chosen day in the UI (the API/optimizer support several).
* Accessibility needs are recorded and warned about; the catalog has no verified accessibility data to filter on.
* Admission costs in the budget come from place records x travellers; avoid also entering them as expenses.
* PostGIS-specific migration code is guarded and was **not** executed in this environment (no PostGIS available).
