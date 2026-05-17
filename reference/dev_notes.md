# Dev Notes

## 2026-05-17 00:03 — Phase 3: Data selection UI

Branch: `phase-3-data-selection-ui` → PR #4

### What changed

- **`app/selectors.py`** — Five option-builder functions used by the layout and callbacks:
  - `topic_options()` — from `HIGHLEVEL_GROUP_DESC`, no network call
  - `vintage_options()` — from `Endpoint.vintages`, LRU-cached, falls back to `range(2023, 2008, -1)` on error
  - `scope_options()` — from `SCOPES.keys()`, LRU-cached, falls back to `[]`
  - `sumlevel_options()` — from `morpc.SUMLEVEL_DESCRIPTIONS`, LRU-cached, falls back to `[]`
  - `group_options_for_topic(topic_code, vintage)` — filters `Endpoint.groups` by `code[1:3] == topic_code`, LRU-cached per topic+vintage, falls back to `[]`

- **`app/layout.py`** — Full Dash layout with dbc.Card holding two rows of selectors (topic+group; vintage+scope+sumlevel) and a disabled Fetch button. Topic/vintage/scope/sumlevel options are populated at layout creation time; group options start empty.

- **`app/callbacks.py`** — Two callbacks registered via `register_callbacks(app)`:
  - `update_group_options(topic_code)` → repopulates group dropdown when topic changes
  - `toggle_fetch_button(...)` → enables Fetch only when all five selectors have a value
  - Business logic split into `compute_group_options()` and `compute_fetch_button_disabled()` (plain functions, testable without Dash context)

- **`app/main.py`** — Replaced placeholder layout with `make_layout()` + `register_callbacks(app)`

- **`tests/test_selectors.py`** — Tests for all five selector functions; network-dependent ones use mocked `Endpoint` objects
- **`tests/test_callbacks.py`** — Tests for `compute_group_options` and `compute_fetch_button_disabled`

### Key decisions

- Callback logic extracted into plain functions (`compute_*`) because Dash-decorated callbacks require the Dash server context and can't be called directly in unit tests.
- `scope_options` and `sumlevel_options` fall back to `[]` when morpc fails (the `morpc` package makes a Census API network call on import that fails in some dev environments).
- `lru_cache(maxsize=len(HIGHLEVEL_GROUP_DESC))` on `group_options_for_topic` avoids re-fetching groups when a user switches between topics they've already visited.

---

## 2026-05-17 00:03 — Phase 2: Database cache layer

Branch: `phase-2-database-cache` → PR #2

### What changed

- **`app/models.py`** — Two SQLAlchemy ORM models:
  - `CensusLongRow` (`census_long` table): stores individual rows from `CensusAPI.long`, keyed by `(survey, vintage, group_code, scope, sumlevel)`. Value columns map 1:1 from the long DataFrame. The `total` column from the DataFrame is stored as `total_val` to avoid SQL keyword conflicts.
  - `GeometryCache` (`geometry_cache` table): stores TIGERweb boundary geometries as PostGIS `GEOMETRY(GEOMETRY, 4326)`, keyed by `(scope, sumlevel, vintage, geoidfq)`. `vintage=NULL` means the `current` TIGERweb service was used.

- **`app/cache.py`** — Four helper functions:
  - `get_census_long` / `put_census_long`: read/write the `census_long` table; `put` deletes existing rows for the key before inserting so cache entries are always replaced atomically.
  - `get_geometry` / `put_geometry`: read/write the `geometry_cache` table; handles `GEOIDFQ`/`NAME` column casing from `fetch_geos_from_scope_sumlevel`.

- **`alembic/versions/001_initial_tables.py`** — Initial migration creating both tables and lookup indexes on their cache key columns. Written manually (no live DB at dev time).

- **`tests/test_models.py`** — Structural tests verifying column sets and constraints.
- **`tests/test_cache.py`** — Unit tests for all four cache helpers using `MagicMock` sessions (no live DB required).

### Key decisions

- `to_shape` / `from_shape` from `geoalchemy2.shape` imported at module level so tests can patch them via `app.cache.*`.
- Geometry type stored as generic `GEOMETRY` (not `MULTIPOLYGON`) because TIGERweb sometimes returns mixed types.
- `vintage=None` for current-service geometry is a deliberate nullable FK; the unique constraint on `(scope, sumlevel, vintage, geoidfq)` still works because NULL is treated as distinct in PostgreSQL unless the same row is inserted twice.

---

## 2026-05-16 23:48 — Phase 1: Initial project scaffold

Branch: `main` (initial commit)

### What changed

- `pyproject.toml`, `.env.example`, `.gitignore`, `Dockerfile`, `compose.yml` — project files
- `app/main.py` — minimal Dash/Bootstrap placeholder app (port 8050)
- `app/db.py` — SQLAlchemy `engine`, `SessionLocal`, `Base`
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako` — Alembic scaffold; `DATABASE_URL` is read from environment in `env.py` so `alembic.ini` stays credential-free

### Key decisions

- `python:3.12-slim` base image with `libgdal-dev` and `libpq-dev` for geopandas and psycopg2.
- PostGIS service (`postgis/postgis:16-3.4`) with health check; app depends on `service_healthy` so migrations can run before the app starts.
