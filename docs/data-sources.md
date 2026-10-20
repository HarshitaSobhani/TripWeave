# Data sources and attribution

* **Place catalog** (`backend/app/seed/data.py`): 10 Paris and 10 Rome landmarks. Coordinates are approximate
  public landmark locations (4 decimals), cross-checked against OpenStreetMap data (ODbL). The catalog intentionally
  contains **no** opening hours, admission prices or visit durations because none were verified. Users supply them
  per place or per trip; hours require a source and are timestamped when stored; costs carry currency and timestamp.
  Each place references a `sources` row (name, URL, license, attribution).
* **Map tiles:** OpenStreetMap standard tiles, attribution shown on the map: (c) OpenStreetMap contributors, ODbL.
  The default `tile.openstreetmap.org` server is governed by the [OSM Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/);
  use your own or a commercial provider for production (`MAP_TILE_URL`, `MAP_TILE_ATTRIBUTION`).
* **Routing (optional):** any OSRM-compatible server (`/table/v1/{profile}/...`). Project OSRM data derives from OpenStreetMap contributors.
* **Currency conversion (optional):** Frankfurter (ECB reference rates, informational). Responses are validated, and the rate, date and provider are shown with the converted total.
* **Not used:** no weather, transit timetable or live availability data.

To add destinations, append to `DESTINATIONS`/`PLACES` with verifiable coordinates and a source, then run `python -m app.seed` (idempotent).
