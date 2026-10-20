# API

Interactive OpenAPI: `GET /docs` and `/openapi.json`. Auth: `Authorization: Bearer <token>`.
Trips and their children are private: another user's trip returns **404**.

## Auth
| | |
|---|---|
| `POST /api/auth/register` `{email,password>=8}` | 201 `{access_token}` (409 if the email exists) |
| `POST /api/auth/login` | `{access_token}` |
| `GET /api/auth/me` | current user |

## Catalog
| | |
|---|---|
| `GET /api/config` | routing/fx provider flags, tile URL + attribution |
| `GET /api/destinations` | list |
| `GET /api/places?destination_id=&q=&category=` | curated places + the caller's own |
| `POST /api/places` | custom place (private). `opening_hours` requires `opening_hours_source`; `cost` requires `cost_currency` |

## Trips
| | |
|---|---|
| `GET/POST /api/trips` | list / create (validates dates, windows, budget, constraints) |
| `GET/PUT/DELETE /api/trips/{id}` | trip with days, stops, candidates, pins, `latest_run` |
| `PUT /api/trips/{id}/candidates` | add/update `{place_id,status,interest,visit_minutes,hours_override,hours_override_source}` |
| `PATCH/DELETE /api/trips/{id}/candidates/{place_id}` | edit / remove |
| `PUT /api/trips/{id}/pins`, `DELETE .../pins/{place_id}` | pin a place to a day |

## Optimization and editing
| | |
|---|---|
| `POST /api/trips/{id}/optimize` `{solver, replace_manual, confirm_replace_manual, interest_weight, balance_weight, preview}` | Returns `{result, run_id, persisted, trip}`. `preview=true` persists nothing. 409 when replacing manual edits is unconfirmed. |
| `POST /api/trips/{id}/reschedule` | Recompute times for the current order, never reorders |
| `POST /api/trips/{id}/stops` `{place_id,day_index,position?,visit_minutes?,notes?}` | add a manual stop |
| `PATCH /api/trips/{id}/stops/{sid}` `{day_index?,position?,visit_minutes?,notes?,locked?}` | move/edit |
| `DELETE /api/trips/{id}/stops/{sid}?forget=` | remove (candidate becomes `excluded`, or deleted with `forget=true`) |
| `GET /api/trips/{id}/runs`, `GET .../runs/{rid}` | run history, parameters, input snapshot, result |
| `POST /api/trips/{id}/runs/{rid}/reproduce` | re-solve from the snapshot |

Result payload: `status` (`feasible|infeasible|empty`), `days[].stops[]` with `arrive/start/end/wait`,
`travel_minutes` + `travel_basis` (`routed|user_buffer`), `distance_m` + `distance_kind`, `unscheduled[]`, `issues[]`
(`error|warning|info`), `explanation[]`, `metrics` (with `before` when a previous plan existed), `matrix_kind`, `params`.

## Budget and export
| | |
|---|---|
| `GET/POST /api/trips/{id}/expenses`, `PUT/DELETE .../{eid}` | categories: food, transport, admission, accommodation, other |
| `GET /api/trips/{id}/budget` | totals per currency, planned admission, optional converted total with rate/date/provider |
| `GET /api/trips/{id}/export?format=json\|csv\|ics` | download. CSV neutralises formula injection; ICS uses floating local times and skips untimed stops |
