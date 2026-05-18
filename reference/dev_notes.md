# Dev Notes

## 2026-05-18 — Value/percent/MOE UI redesign

Branch: `main` (direct commit)

### What changed

- **`app/fetch.py`** — `build_wide_table` signature changed: `value_mode: str = "estimate"` and `show_moe: bool = False` replace the old `value_types: list[str]` parameter. When `value_mode == "percent"`, calls `DimensionTable.percent()`; otherwise `DimensionTable.wide()`. `show_moe` controls whether the MOE value_type is kept alongside the primary values.

- **`app/exports.py`** — `export_excel` signature changed: `value_mode: str = "estimate"` and `show_moe: bool = False` replace `value_types`. Same dispatch logic as `build_wide_table`.

- **`app/layout.py`** — Value-type checklist (`dbc.Checklist(id="value-type-checklist")`) replaced with two controls:
  - `dbc.RadioItems(id="value-mode-radio")` — mutually exclusive Estimate / Percent choice, default "estimate"
  - `dbc.Checkbox(id="show-moe-checkbox")` — toggles MOE column display, default False

- **`app/callbacks.py`** — Cascading signature updates:
  - `compute_table(store_data, value_mode, show_moe)` — passes both args to `build_wide_table`
  - `compute_excel_download(store_data, group_code, vintages, value_mode, show_moe)` — passes both args to `export_excel`; guard changed from `not value_types` to `not store_data or not group_code`
  - `render_table` callback: `Input("value-type-checklist", "value")` → `Input("value-mode-radio", "value")` + `Input("show-moe-checkbox", "value")`
  - `download_excel` callback: same replacement in `State`

- **Tests** — Updated to new signatures:
  - `test_fetch.py`: `TestBuildWideTable` and `TestComputeTable` use positional `"estimate", False` / `"estimate", True`
  - `test_exports.py`: `TestExportExcel` and `TestComputeExcelDownload` use new `(value_mode, show_moe)` args; `test_returns_no_update_when_no_value_types` replaced with `test_returns_no_update_when_no_group`

### Design note

The old checklist allowed zero selections (making the card vanish) and didn't cleanly separate "which pivot to use" from "show MOE alongside". RadioItems enforces exactly one mode and the checkbox orthogonally toggles MOE, matching how `DimensionTable.wide()` / `DimensionTable.percent()` actually work.

## 2026-05-18 — Multi-geography + chart tab (items 3 & 4)

Branch: `main` (direct commit)

### What changed

- **`pyproject.toml`** — Added `plotnine>=0.13` to dependencies.

- **`app/fetch.py`** — Added `fetch_all_geos(session, group_code, vintages, geo_list)`. Loops over a list of `{"scope": str, "sumlevel": str}` dicts, calls `fetch_all_vintages` for each, and concatenates the results. Empty frames are filtered before concat.

- **`app/layout.py`** — Two structural changes:
  - **Multi-geography selection**: Row 2 (`vintage / scope / sumlevel`) gains an "Add Geography" button (col md=2, scope/sumlevel columns narrowed to md=3). A new `geo-chips` div below Row 2 shows the selected geographies as inline `dbc.Badge + html.Button("×")` chips. A `dcc.Store(id="geo-list-store", data=[])` holds the list.
  - **Tabbed output**: Table and chart are now in `dbc.Tabs` (tab-table / tab-chart). Chart tab has four `dcc.Dropdown` controls (X axis, Y axis, Color by, Chart type) and a `html.Img(id="chart-image")`. `dcc.Loading` wrappers moved inside each tab.

- **`app/callbacks.py`** — Several additions and changes:
  - `compute_fetch_button_disabled` signature changed: `scope`/`sumlevel` replaced by `geo_list: list | None`. Button enabled when topic + group + vintages set AND geo_list is non-empty.
  - `compute_fetch_and_store` signature changed: `scope`/`sumlevel` replaced by `geo_list`. Internally calls `fetch_all_geos`.
  - `compute_geo_list(n_add, n_removes, scope, sumlevel, current_list, trigger_id)` — pure function (trigger_id passed explicitly from `dash.ctx.triggered_id` in the registered callback so it's testable outside Dash). Handles add-geo-btn and pattern-matching remove-geo triggers.
  - `compute_geo_chips(geo_list)` — renders inline badge + close-button Span elements.
  - `compute_frictionless_download` signature changed: `scope`/`sumlevel` replaced by `geo_list`; uses `geo_list[0]` for CensusAPI metadata.
  - `render_chart_image(long_df, x_col, y_col, color_col, chart_type)` — lazy-imports plotnine; renders bar/line/point chart as base64 PNG data URI; returns `""` if plotnine unavailable or render fails.
  - New Dash callbacks: `update_geo_list`, `render_geo_chips`, `update_chart`.
  - `toggle_fetch_button` now inputs `geo-list-store.data` instead of `scope-dropdown.value` / `sumlevel-dropdown.value`.
  - `fetch_and_store` now States `geo-list-store.data` instead of scope/sumlevel dropdowns.

- **Tests** — Updated throughout:
  - `test_callbacks.py`: new `TestComputeGeoList`, `TestComputeGeoChips`, `TestRenderChartImage`; updated `TestComputeFetchButtonDisabled` and `TestComputeFetchAndStore`.
  - `test_fetch.py`: new `TestFetchAllGeos`; updated `TestComputeFetchAndStore` to patch `fetch_all_geos`.
  - `test_exports.py`: `TestComputeFrictionlessDownload` updated for geo_list param.

### Design note: plotnine geom_line warning
A `PlotnineWarning: geom_path: Each group consist of only one observation` appears in the line-chart test because the fixture has only 1 observation per group. This is expected in tests and harmless in production.

## 2026-05-18 — Export improvements (items 1 & 2)

Branch: `main` (direct commit)

### What changed

- **`app/exports.py`** — Two improvements:
  - `export_frictionless` now uses `CensusAPI.save()` for richer metadata (proper frictionless schema introspection, universe, concept, variable descriptions). Signature extended: `scope` and `sumlevel` added as required args. The function calls `CensusAPI.save()` for the earliest selected vintage to generate `.schema.yaml` and `.resource.yaml`, then overwrites the CSV with the (possibly multi-vintage) `long_df`. The `_frictionless_type` helper is removed (no longer needed).
  - `export_excel` now uses `morpc.plot.excel.ExcelChart` exclusively — pandas `ExcelWriter` fallback removed. Raises `RuntimeError` if morpc is not importable (PyPI release fails at import-time due to Census API call; vendor wheel in container is fine).

- **`app/callbacks.py`**:
  - `compute_frictionless_download` gains `scope` and `sumlevel` parameters; passes them to `export_frictionless`.
  - `download_frictionless` callback adds `State("scope-dropdown", "value")` and `State("sumlevel-dropdown", "value")`.

- **`tests/test_exports.py`** — Full rewrite of export tests:
  - `_FakeExcelChart`: xlsxwriter-backed stand-in for `morpc.plot.excel.ExcelChart`, used in local test env where PyPI morpc fails to import.
  - `_mock_census_api`: creates `MagicMock` with `.save()` side-effect that writes placeholder files so `export_frictionless` can be tested without Census API calls.
  - Removed `test_falls_back_to_pandas_when_exclechart_fails` (fallback no longer exists); added `test_raises_when_exclechart_unavailable`.
  - All frictionless tests patched through `_export_frictionless_mocked` helper; all Excel tests patch `app.exports.ExcelChart` with `_FakeExcelChart`.
  - `TestComputeFrictionlessDownload` updated: new `scope`/`sumlevel` args; CensusAPI patched in integration tests.

## 2026-05-17 — Phase 6: Polish

Branch: `phase-6-polish` → PR #10

### What changed

- **`app/assets/custom.css`** — MORPC brand theme via CSS custom properties:
  - `--morpc-green: #8DC63F`, `--morpc-green-dark: #6E9F3A`, `--morpc-green-light: #E3F0D6`, `--morpc-blue: #064A8C`, `--morpc-sky: #74C3D5`
  - `.morpc-header`: blue header bar (white text, rounded corners, bottom margin)
  - `.btn-primary`: green Fetch Data button (hover → dark green)
  - `.btn-outline-secondary`: blue-bordered export buttons
  - `.card`: green left accent border on all cards
  - `.dash-header` / `.dash-filter`: light green table header bg, sky-blue filter row focus ring

- **`app/layout.py`** — Three additions:
  - `html.H2` wrapped in `html.Div(className="morpc-header")` for branded header
  - `dbc.Alert(id="fetch-error-alert", color="danger", is_open=False, dismissable=True)` just below header
  - `dcc.Loading(type="default", color="var(--morpc-green)")` wrapping the `data-output` div for spinner during fetch

- **`app/callbacks.py`** — Two additions:
  - `_friendly_error(exc)`: classifies `OperationalError` / `TimeoutError` / `KeyError` / generic exceptions into readable messages
  - `compute_fetch_and_store` extended to 4-tuple return `(store_data, status_text, error_message, error_is_open)`; empty DataFrame now surfaces as an alert rather than silently showing no table; `fetch_and_store` callback wired to two additional outputs (`fetch-error-alert.children`, `fetch-error-alert.is_open`)

- **`.github/workflows/ci.yml`** — GitHub Actions CI running on push/PR:
  - Matrix: Python 3.10, 3.11, 3.12
  - Steps: checkout → setup-python (pip cache) → `pip install -e ".[dev]"` → `ruff check` → `pytest tests/ -q`
  - `DATABASE_URL` set to a fake local URL (tests mock the DB layer, no live DB needed)

- **`tests/test_callbacks.py`** — Added `TestFriendlyError` (3 tests) and `TestComputeFetchAndStore` (4 tests) covering success, exception-opens-alert, and empty-DataFrame-opens-alert paths
- **`tests/test_fetch.py`** — Updated two existing tests to unpack the new 4-tuple from `compute_fetch_and_store`

### Key decisions

- `_friendly_error` classifies by exception type name rather than `isinstance` so it works even when morpc-census exception classes aren't importable in the test environment.
- Empty DataFrame surfaces as an alert (not a silent no-op) because users otherwise see a spinner that never resolves into a table.
- `dcc.Loading` wraps only `data-output` (not the whole page) so the selector card remains interactive while a fetch is in progress.
- CI uses `DATABASE_URL=postgresql://morpc:x@localhost/morpc_census` but all DB calls in tests are mocked — no live DB is needed for CI to pass.

---

## 2026-05-17 00:03 — Phase 5: Export

Branch: `phase-5-export` → PR #8

### What changed

- **`app/exports.py`** — Two export functions:
  - `export_frictionless(long_df, group_code, vintages)`: writes long CSV + auto-generated frictionless schema YAML + resource YAML to a temp dir, zips all three, returns bytes. Uses `frictionless` package directly rather than `CensusAPI.save()` (which requires the full API object with variable metadata). Field types are inferred from pandas dtypes.
  - `export_excel(long_df, group_code, value_types)`: pivots via `DimensionTable.wide()`, filters to selected value types, writes to BytesIO. Tries `morpc.plot.ExcelChart` first; falls back to `pandas.ExcelWriter(engine='xlsxwriter')` when morpc fails to import (morpc triggers a Census API network call on `__init__`). `ExcelChart` imported at module level (with try/except) so tests can patch `app.exports.ExcelChart`.

- **`app/layout.py`** — Added `dcc.Download` components (`download-frictionless`, `download-excel`) and two `dbc.Button` export buttons inside the value-type filter card.

- **`app/callbacks.py`** — Added:
  - `compute_frictionless_download` / `download_frictionless`: triggered by Frictionless button click; reads Store + group/vintage State; returns `dcc.send_bytes()` payload
  - `compute_excel_download` / `download_excel`: same pattern for Excel; also reads value-type checklist State
  - `logger` added at module level; `dcc` imported at module level for `dcc.send_bytes`

- **`pyproject.toml`** — Added `frictionless>=5.0` and `xlsxwriter>=3.0` as explicit dependencies (they were already available transitively via morpc-census and morpc)

- **`tests/test_exports.py`** — 20 tests covering zip structure/contents, xlsx format, fallback path, and download callback return values

### Key decisions

- Frictionless export does NOT use `CensusAPI.save()`: that method requires the full `CensusAPI` object (for `define_schema()` which needs `self.vars`). For multi-vintage data, we'd need one API object per vintage anyway. Using `frictionless` directly from the DataFrame is simpler and handles multi-vintage naturally.
- `ExcelChart` imported at module level with a silent `except Exception: ExcelChart = None` so that: (1) the module is always importable, and (2) the name is patchable in tests. When `None`, `ExcelChart(...)` raises `TypeError` which is caught by the existing try/except, triggering the pandas fallback.
- Excel export filters to the same value types the user has selected in the checklist, so the download matches what they see in the table.

---

## 2026-05-17 00:03 — Phase 4: Data fetch and table display

Branch: `phase-4-data-fetch-display` → PR #6

### What changed

- **`app/fetch.py`** — Core fetch/pivot module:
  - `fetch_long_for_vintage`: reads PostGIS cache first; on miss, calls `CensusAPI(endpoint, scope, group, sumlevel)`, writes result to cache, returns `.long`
  - `fetch_all_vintages`: loops over selected vintages, concatenates `.long` DataFrames; multi-vintage comparison works naturally because `reference_period` becomes a column-level in `DimensionTable.wide()`
  - `build_wide_table`: calls `DimensionTable(long_df).wide()`, filters by selected value types, flattens MultiIndex to flat column IDs, returns `(data, columns)` for `dash_table.DataTable`
  - `serialise_long` / `deserialise_long`: round-trip via `orient='split'`; `deserialise_long` casts `reference_period` back to int (JSON coerces ints to floats)

- **`app/layout.py`** — Added:
  - `dcc.Store(id="long-data-store")` for persisting long DataFrame between callbacks
  - Status text next to Fetch button
  - Value-type checklist card (hidden until data loads): Estimate / MOE / Percent Estimate / Percent MOE, default Estimate
  - `data-output` div renders the DataTable

- **`app/callbacks.py`** — Added two new callbacks (plus `compute_*` plain functions):
  - `compute_fetch_and_store` / `fetch_and_store`: button click → fetches all vintages → writes to `long-data-store`; `SessionLocal()` is inside the try block so DB errors surface as status messages
  - `compute_table` / `render_table`: triggered by Store change or checklist change → pivots and renders `dash_table.DataTable` with native sort + filter; also toggles visibility of the value-type card
  - `Endpoint`, `Group`, `CensusAPI`, `DimensionTable`, `SessionLocal` all imported at module level so tests can patch them via `app.fetch.*` / `app.callbacks.*`

- **`tests/test_fetch.py`** — 19 tests covering all fetch functions and round-trip serialisation

### Key decisions

- `Endpoint`, `Group`, `CensusAPI`, `DimensionTable` moved to module-level imports in `fetch.py` (lazy imports inside functions block `patch()` in tests)
- `SessionLocal()` moved inside the `try` block so connection failures are caught and returned as status messages rather than crashing the callback
- `build_wide_table` iterates `wide.iterrows()` directly (avoids `reset_index()` complexity with mixed-type MultiIndex columns)
- MultiIndex column IDs are joined with `__` as separator; the `__dim_N__` prefix identifies dimension/row-label columns in the DataTable

---

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
