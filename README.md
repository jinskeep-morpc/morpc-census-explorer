# morpc-census-explorer

A Dash web application for exploring US Census ACS 5-year data.

Select a topic, browse variable groups, pick one or more vintages, choose a
geographic scope and resolution, and view the results in an interactive table.
Data can be exported to Excel (with embedded charts) or as raw CSV with
frictionless metadata.

Powered by [morpc-census](https://github.com/jinskeep-morpc/morpc-census).
Census data and geometry are cached in PostGIS so repeat queries are fast.

---

## Quick start

```bash
cp .env.example .env          # fill in CENSUS_API_KEY and DB_PASSWORD
podman compose up
```

Open http://localhost:8050

---

## Dev setup

```bash
pip install -e ".[dev]"
# set DATABASE_URL and CENSUS_API_KEY in .env or environment
python -m app.main
```

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `CENSUS_API_KEY` | Census Bureau API key ([get one here](https://api.census.gov/data/key_signup.html)) |
| `DB_PASSWORD` | PostgreSQL password |
| `DATABASE_URL` | Full SQLAlchemy connection string (set automatically in Compose) |
| `EXPORT_DIR` | Directory for downloaded export files (default: `./exports`) |

---

## Roadmap

### Phase 1 — Project scaffolding

- [x] Repo, `pyproject.toml`, `.env.example`, `.gitignore`
- [x] `Dockerfile` and `compose.yml` (app + PostGIS services)
- [x] Minimal Dash app that starts and returns a placeholder page
- [x] DB connection via SQLAlchemy + Alembic scaffold

### Phase 2 — Database cache layer

- [x] `census_long` table: stores long-format DataFrames keyed by `(survey, vintage, group, scope, sumlevel)`
- [x] `geometry_cache` table: PostGIS geometry column keyed by `(scope, sumlevel, vintage, geoid)`
- [x] Cache read/write helpers in `app/cache.py`
- [x] Alembic initial migration

### Phase 3 — Data selection UI

- [x] Topic dropdown (from `HIGHLEVEL_GROUP_DESC`)
- [x] Group browser filtered by topic
- [x] Multi-select vintage picker
- [x] Scope selector
- [x] SumLevel selector
- [x] Chained Dash callbacks: each selector populates the next

### Phase 4 — Data fetch and table display

- [x] Cache-first fetch: check PostGIS, fall back to Census API and write result to cache
- [x] Concatenate long DataFrames across selected vintages
- [x] Pivot with `DimensionTable.wide()` and display in `dash_table.DataTable`
- [x] Column filter for value type (estimate / MOE / percent)

### Phase 5 — Export

- [x] Frictionless export: `CensusAPI.save()` → zip download
- [x] Excel export: `morpc.plot.ExcelChart` → `.xlsx` download
- [x] Download buttons in the UI

### Phase 6 — Polish

- [x] Loading spinners during fetch
- [x] User-facing error messages (bad scope/sumlevel combo, API timeout)
- [x] MORPC colour theme applied to Dash components
- [x] CI: GitHub Actions running lint + import check
- [x] Fix sidebar dropdowns rendering behind DataTable/chart (remove overflow clipping, add z-index CSS)

---

This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau.
