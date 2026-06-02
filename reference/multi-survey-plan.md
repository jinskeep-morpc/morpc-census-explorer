# Multi-Survey Implementation Plan

**Branch:** `feature/multi-survey`  
**Issue:** #57  
**Target surveys:**

| Survey ID | Name | Vintages |
|-----------|------|----------|
| `acs/acs1` | ACS 1-Year Estimates | 2005–present (most years) |
| `acs/acs5` | ACS 5-Year Estimates | 2009–present |
| `dec/pl` | P.L. 94-171 Redistricting Data | 2010, 2020 |
| `dec/dhc` | Demographic and Housing Characteristics | 2020 |
| `dec/sf1` | Summary File 1 | 2010 |

---

## Key differences between surveys

| Property | ACS (acs1, acs5) | Decennial (dec/*) |
|----------|------------------|-------------------|
| MOE columns | Yes | No |
| Percent columns | Sometimes | No |
| Group code prefix | `B`, `C`, `S` | `P`, `H`, `PCT` |
| Topic taxonomy | HIGHLEVEL_GROUP_DESC (01–99) | Different — groups don't use same prefix scheme |
| Vintages | Annual (many) | 2010, 2020 only |
| `variable_label` | Long descriptive text | Shorter |

---

## Architecture: what changes

### 1. Survey registry (`app/selectors.py`)

**New: `SURVEYS` dict** — replaces the hardcoded `SURVEY = "acs/acs5"` constant.

```python
SURVEYS = {
    "acs/acs5": {
        "label": "ACS 5-Year Estimates",
        "short": "ACS5",
        "default_vintage": 2024,
        "has_moe": True,
        "topic_prefix": True,   # groups use HIGHLEVEL_GROUP_DESC prefix scheme
        "source_url": "https://www.census.gov/data/developers/data-sets/acs-5year.html",
    },
    "acs/acs1": {
        "label": "ACS 1-Year Estimates",
        "short": "ACS1",
        "default_vintage": 2023,
        "has_moe": True,
        "topic_prefix": True,
        "source_url": "https://www.census.gov/data/developers/data-sets/acs-1year.html",
    },
    "dec/pl": {
        "label": "Decennial Census: Redistricting Data (P.L. 94-171)",
        "short": "DEC-PL",
        "default_vintage": 2020,
        "has_moe": False,
        "topic_prefix": False,
        "source_url": "https://www.census.gov/data/developers/data-sets/decennial-census.html",
    },
    "dec/dhc": {
        "label": "Decennial Census: Demographic and Housing Characteristics",
        "short": "DEC-DHC",
        "default_vintage": 2020,
        "has_moe": False,
        "topic_prefix": False,
        "source_url": "https://www.census.gov/data/developers/data-sets/decennial-census.html",
    },
    "dec/sf1": {
        "label": "Decennial Census: Summary File 1",
        "short": "DEC-SF1",
        "default_vintage": 2010,
        "has_moe": False,
        "topic_prefix": False,
        "source_url": "https://www.census.gov/data/developers/data-sets/decennial-census.html",
    },
}
```

**Updated functions:**
- `survey_options()` — new, returns `[{label, value}]` from SURVEYS
- `vintage_options(survey)` — now parameterised by survey; fetches from the given Endpoint
- `topic_options(survey)` — for ACS surveys, returns HIGHLEVEL_GROUP_DESC; for decennial, returns a flat list of all group prefixes from the Endpoint
- `group_options_for_topic(topic_code, survey, vintage)` — add survey param; decennial groups are fetched differently

### 2. Layout (`app/layout.py`)

**New: Survey dropdown** — add as the first element of "1. Select Data" accordion step, before Topic.  
ID: `survey-dropdown`  
Options: from `survey_options()`  
Default: `"acs/acs5"`

**Topic dropdown** — only shown/enabled for surveys with `topic_prefix=True`; hidden for decennial surveys (they don't share the ACS topic taxonomy).

**Group dropdown** — always shown; options come from `group_options_for_topic(topic, survey, vintage)`.

**Vintage dropdown** — options come from `vintage_options(survey)`, re-populated when survey changes.

**Values / MOE section** — "Show margin of error" checkbox and "Percent" mode should only be enabled when the selected survey has `has_moe=True`.

**Tooltip text** — update the Vintage tooltip to mention that different surveys cover different year ranges.

### 3. Callbacks (`app/callbacks.py`)

**New State/Input threads:**
- `survey-dropdown` value is threaded into every callback that currently reads from `SURVEY`.
- `survey-dropdown` triggers `update_group_options` and `update_vintage_options`.

**`update_vintage_options`** — new callback; triggers on survey change; calls `vintage_options(survey)`.

**`update_group_options`** — add `survey` as input; pass to `group_options_for_topic`.

**`update_moe_controls`** — show/hide the MOE checkbox and percent radio based on `SURVEYS[survey]["has_moe"]`.

**`fetch_data`** — replace `SURVEY` constant with the State value of `survey-dropdown`.

**Chart title** — replace "American Community Survey 5-Year Estimates" hardcoded caption with `SURVEYS[survey]["label"]`.

**Download filenames** — replace `census-acs5-{group}-{vintage}` with `census-{short}-{group}-{vintage}` where `short` is `SURVEYS[survey]["short"].lower()`.

### 4. Fetch (`app/fetch.py`)

**`fetch_long_for_vintage`** — add `survey` parameter; use it in place of the imported `SURVEY` constant for `Endpoint(survey, vintage)` and the cache key.

**`fetch_all_vintages`** — add `survey` param; pass through.

**`fetch_all_geos`** — add `survey` param; pass through.

### 5. Exports (`app/exports.py`)

**`SURVEY` constant** — remove; derive from `long_df["survey"]` (already done for the table description; extend to `_CENSUS_SOURCE` URL and README.txt).

**`_CENSUS_SOURCE`** — make dynamic: read the survey from `long_df`, look it up in `SURVEYS`, use its `source_url`.

**Package keywords** — replace `["census", "acs", "acs5", ...]` with survey-agnostic terms + the survey short code.

**`export_frictionless`** — add `survey` param or derive from `long_df["survey"]`; use it for the `Endpoint()` call and the `_CENSUS_SOURCE` URL.

**README.txt** — remove ACS 5-Year-specific language; make generic to "Census data via the Census API."

### 6. Selectors (`app/selectors.py`)

- Remove `SURVEY = "acs/acs5"` module-level constant (used in 4 places — all must become dynamic).
- `vintage_options(survey)` — drop `@lru_cache` or use `@lru_cache` keyed on `survey`.
- `group_options_for_topic(topic_code, survey, vintage)` — add survey param.

### 7. Cache (`app/cache.py` / `app/models.py`)

The cache already stores `survey` as part of the key — no schema change needed. The `CensusLongRow` model has `survey: Mapped[str]`. The fetch helpers just need the `survey` param threaded through.

---

## Implementation order

Work in this sequence to keep the app functional at each step:

1. **Add survey registry to `selectors.py`** and `survey_options()`.  Add `survey-dropdown` to layout with `acs/acs5` as default. No other changes yet — the app keeps working.

2. **Parameterise `vintage_options(survey)`** and wire up the cascade callback (`survey → vintages`).

3. **Parameterise `topic_options(survey)` and `group_options_for_topic(topic, survey, vintage)`**. Add survey to the group cascade callback. Show/hide topic dropdown for decennial surveys.

4. **Thread `survey` through fetch** — `fetch_long_for_vintage`, `fetch_all_vintages`, `fetch_all_geos`, and the main fetch callback. Remove the `from app.selectors import SURVEY` import from `fetch.py`.

5. **Update UI controls** — disable MOE checkbox and Percent mode when `has_moe=False`; update chart caption and download filenames.

6. **Update exports** — remove `SURVEY` from `exports.py`; derive census source URL from survey; fix README.txt and package keywords.

7. **Test each survey end-to-end**: fetch, display table, display chart, export zip.

---

## Files changed

| File | Change summary |
|------|---------------|
| `app/selectors.py` | Add `SURVEYS`, `survey_options()`, parameterise `vintage_options`, `topic_options`, `group_options_for_topic` |
| `app/layout.py` | Add `survey-dropdown`; conditionally show topic; update tooltip text |
| `app/callbacks.py` | Thread `survey` through all callbacks; add `update_vintage_options`; update MOE controls, captions, filenames |
| `app/fetch.py` | Add `survey` param to all fetch helpers; remove `SURVEY` import |
| `app/exports.py` | Remove `SURVEY` import; derive source URL and keywords from `long_df["survey"]`; fix README.txt |
| `tests/test_fetch.py` | Update fixture calls to include `survey` param |
| `tests/test_exports.py` | Update mock and assertions for multi-survey |
| `tests/test_callbacks.py` | Update for survey dropdown state |

---

## Open questions / risks

- **Decennial topic taxonomy**: `dec/*` groups do not follow the `B01001`-style two-digit prefix scheme. The topic dropdown should be hidden for decennial surveys; the group dropdown should show all groups from the endpoint (or allow text search).
- **ACS 1-Year geography gaps**: `acs/acs1` only covers areas with population ≥ 65,000. Some scope/sumlevel combinations will return empty data — the app should surface a clear error rather than showing an empty table.
- **Percent mode**: Decennial data has no MOE and no percent columns. The "Values" radio and MOE checkbox should be hidden or disabled when `has_moe=False`.
- **DimensionTable compatibility**: `DimensionTable` works on `CensusAPI.long` regardless of survey. No morpc-census changes needed for the core dimension logic.
- **Cache key**: Already includes `survey` — no migration needed.
