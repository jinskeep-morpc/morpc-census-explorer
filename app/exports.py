"""Export helpers: frictionless zip and Excel downloads."""

from __future__ import annotations

import contextlib
import io
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import frictionless
import pandas as pd
import yaml as _yaml
from morpc_census.api import CensusAPI, DimensionTable, Endpoint, Group

# morpc makes a Census API network call at import time in the PyPI release;
# the vendor wheel used in the container has this removed, so this is safe
# there. Wrap the import so the module stays importable in test environments
# that only have the PyPI version installed.
try:
    from morpc.plot.excel import ExcelChart
except Exception:
    ExcelChart = None  # type: ignore[assignment,misc]

from app.selectors import SURVEY

logger = logging.getLogger(__name__)

_MORPC_SOURCE = {
    "title": "Mid-Ohio Regional Planning Commission (MORPC)",
    "path": "https://www.morpc.org",
}
_CENSUS_SOURCE = {
    "title": "U.S. Census Bureau, American Community Survey 5-Year Estimates",
    "path": "https://www.census.gov/data/developers/data-sets/acs-5year.html",
}
_LICENSE = {
    "name": "CC-BY-4.0",
    "path": "https://creativecommons.org/licenses/by/4.0/",
    "title": "Creative Commons Attribution 4.0",
}

_README_MD = """\
# MORPC Census Data Export

This archive was produced by the
[MORPC Census Explorer](https://github.com/jinskeep-morpc/morpc-census-explorer)
and contains a [Frictionless Data Package](https://specs.frictionlessdata.io/data-package/).

## File structure

All files share a common base name derived from the survey, vintage, geography scope,
summary level, and Census group code — for example:

    census-acs-acs5-2023-county-region10-b01001

| File | Description |
|------|-------------|
| `{base}.package.yaml` | **Start here.** Frictionless Data Package descriptor listing all resources with titles, descriptions, and full metadata (concept, universe, geographies, vintages, license). |
| `{base}.long.csv` | Raw long-format Census data. Each row is one variable for one geography and year. Columns: `geoidfq`, `name`, `reference_period`, `survey`, `concept`, `universe`, `variable`, `variable_label`, `estimate`, `moe`. |
| `{base}.long.schema.yaml` | Frictionless Schema for the long CSV — field types, descriptions, primary key, and missing-value codes. |
| `{base}.long.resource.yaml` | Frictionless Resource descriptor for the long CSV (validated). |
| `{base}.table.csv` | **Dimension table.** Flat wide CSV with one row per dimension combination and one column per geography–year–value-type. Dim columns are listed first, followed by data columns named `"{Geography} - {Year} ({Value Type})"`. |
| `{base}.table.schema.yaml` | Frictionless Schema for the dimension table CSV. |
| `{base}.table.resource.yaml` | Frictionless Resource descriptor for the dimension table CSV (validated). |
| `{base}.chart.vega.json` | Vega-Lite chart specification (JSON). Open at <https://vega.github.io/editor> to explore or modify interactively. |
| `{base}.chart.svg` | Rendered chart as a scalable vector graphic. |
| `README.md` | This file. |

> **Note:** Chart files are only present when a chart was visible at export time.

## Data source

Data are from the U.S. Census Bureau American Community Survey (ACS) 5-Year Estimates,
accessed via the [Census API](https://api.census.gov).
Census data are in the public domain.

## Tools

| Package | Description | Repository |
|---------|-------------|------------|
| **morpc-census** | Python library for fetching and processing ACS data via the Census API | <https://github.com/jinskeep-morpc/morpc-census> |
| **morpc-census-explorer** | Dash web application for exploring, filtering, and exporting ACS data | <https://github.com/jinskeep-morpc/morpc-census-explorer> |

## Contact

**Mid-Ohio Regional Planning Commission (MORPC) — Data & Maps Team**
dataandmaps@morpc.org
<https://www.morpc.org>

## License

This package and its metadata are released under the
[Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).
Please credit: *U.S. Census Bureau via MORPC Census Explorer.*
"""


def _long_resource_entry(
    long_df: pd.DataFrame,
    csv_name: str,
    schema_name: str,
    group_code: str,
    vintages: list[int],
    scope: str,
) -> dict:
    """Build a frictionless resource descriptor dict for the raw long CSV."""
    concept  = str(long_df["concept"].dropna().iloc[0])  if "concept"  in long_df.columns else group_code
    universe = str(long_df["universe"].dropna().iloc[0]) if "universe" in long_df.columns else ""
    survey   = str(long_df["survey"].dropna().iloc[0])   if "survey"   in long_df.columns else SURVEY
    year_str = ", ".join(str(v) for v in sorted(vintages))

    return {
        "name": "long-data",
        "title": f"{concept} — raw long-form data ({year_str})",
        "description": (
            f"Raw long-format Census data for {concept} from {survey} ({year_str}), "
            f"{scope}. Each row is one variable for one geography. "
            f"Universe: {universe}."
        ),
        "path": csv_name,
        "schema": schema_name,
        "mediatype": "text/csv",
        "sources": [dict(_CENSUS_SOURCE)],
    }


def _apply_drops(long_df: pd.DataFrame, dropped_dims: list[str] | None) -> DimensionTable:
    """Build a DimensionTable and apply any dropped dims."""
    dt = DimensionTable(long_df)
    for dim in (dropped_dims or []):
        try:
            dt = dt.drop(dim)
        except (IndexError, ValueError, KeyError) as exc:
            logger.warning("DimensionTable.drop(%s) failed during export: %s — skipping", dim, exc)
    return dt


def export_frictionless(
    long_df: pd.DataFrame,
    group_code: str,
    vintages: list[int],
    scope: str,
    sumlevel: str,
    chart_spec: dict | None = None,
    title: str = "",
    dropped_dims: list[str] | None = None,
    value_mode: str = "estimate",
) -> bytes:
    """Return zip bytes containing a Frictionless Data Package.

    All files share the same base name as CensusAPI produces, e.g.
    ``census-acs-acs5-2023-county-franklin-b01001``:

    - ``{base}.long.csv`` / ``.long.schema.yaml`` / ``.long.resource.yaml``
    - ``{base}.table.csv`` / ``.table.schema.yaml`` / ``.table.resource.yaml``
    - ``{base}.chart.vega.json`` / ``.chart.svg`` (when chart_spec given)
    - ``{base}.package.yaml`` — validated Frictionless Data Package descriptor

    All YAML files are written and validated through the frictionless library.
    """
    import json

    vintage = sorted(vintages)[0]
    endpoint = Endpoint(SURVEY, vintage)
    group = Group(endpoint, group_code)
    year_str = ", ".join(str(v) for v in sorted(vintages))

    with tempfile.TemporaryDirectory() as _tmp:
        tmpdir = Path(_tmp)

        # ── 1. Raw long-form data ─────────────────────────────────────────────
        api = CensusAPI(endpoint=endpoint, scope=scope, group=group, sumlevel=sumlevel)
        api.save(tmpdir)
        # Overwrite the stub CSV with the actual (possibly multi-vintage) data
        long_df.to_csv(tmpdir / api.filename, index=False)

        # Use api.name as the shared base for every file in the package
        # e.g. "census-acs-acs5-2023-county-franklin-b01001"
        base = api.name

        # api.save() writes {base}.schema.yaml / {base}.resource.yaml (no .long. infix).
        # Rename the schema, then rebuild the resource via frictionless with the
        # updated path so the file is properly encoded and validated.
        long_csv_name    = f"{base}.long.csv"
        long_schema_name = f"{base}.long.schema.yaml"
        long_res_name    = f"{base}.long.resource.yaml"

        (tmpdir / f"{base}.schema.yaml").rename(tmpdir / long_schema_name)

        old_res_descriptor = _yaml.safe_load(
            (tmpdir / f"{base}.resource.yaml").read_text(encoding="utf-8")
        )
        old_res_descriptor["schema"] = long_schema_name
        long_resource = frictionless.Resource.from_descriptor(old_res_descriptor)
        with contextlib.chdir(tmpdir):
            long_resource.to_yaml(long_res_name)
            result = frictionless.Resource(long_res_name).validate()
        if not result.valid:
            logger.error("Long resource validation failed: %s", result.stats)
            raise RuntimeError("Long resource validation failed after save.")
        (tmpdir / f"{base}.resource.yaml").unlink()

        # ── 2. Dimension table ────────────────────────────────────────────────
        dt = _apply_drops(long_df, dropped_dims)
        table_name = f"{base}.table"   # DimensionTable.save() appends .csv / .schema.yaml / .resource.yaml

        concept  = str(long_df["concept"].dropna().iloc[0])  if "concept"  in long_df.columns else group_code
        universe = str(long_df["universe"].dropna().iloc[0]) if "universe" in long_df.columns else ""
        survey   = str(long_df["survey"].dropna().iloc[0])   if "survey"   in long_df.columns else SURVEY

        if "name" in long_df.columns:
            geo_names = sorted(long_df["name"].dropna().unique().tolist())
        else:
            geo_names = sorted(long_df["geoidfq"].dropna().unique().tolist())

        geo_summary = geo_names[0] if len(geo_names) == 1 else f"{len(geo_names)} geographies"
        dropped_note = (
            f" Dimensions collapsed: {', '.join(dropped_dims)}." if dropped_dims else ""
        )
        table_description = (
            f"Dimension table for {concept} from {survey} ({year_str}), "
            f"{geo_summary}.{dropped_note} Universe: {universe}."
        )
        table_title = title or f"{concept} — dimension table ({year_str})"

        # dt.save() writes the CSV, schema YAML, and a validated resource YAML
        dt.save(tmpdir, table_name, value_mode=value_mode,
                title=table_title, description=table_description)

        table_csv_name    = f"{table_name}.csv"
        table_schema_name = f"{table_name}.schema.yaml"
        table_res_name    = f"{table_name}.resource.yaml"

        # ── 3. Chart artifacts ────────────────────────────────────────────────
        resources = [
            _long_resource_entry(long_df, long_csv_name, long_schema_name, group_code, vintages, scope),
            {
                "name": "dimension-table",
                "title": table_title,
                "description": table_description,
                "path": table_csv_name,
                "schema": table_schema_name,
                "mediatype": "text/csv",
                "_concept":            concept,
                "_universe":           universe,
                "_survey":             survey,
                "_geographies":        geo_names,
                "_vintages":           sorted(vintages),
                "_value_mode":         value_mode,
                "_dimensions_dropped": list(dropped_dims or []),
            },
        ]

        if chart_spec:
            spec_filename = f"{base}.chart.vega.json"
            (tmpdir / spec_filename).write_text(json.dumps(chart_spec, indent=2), encoding="utf-8")
            resources.append({
                "name": "chart-spec",
                "title": "Vega-Lite chart specification",
                "description": (
                    "Vega-Lite JSON specification for the rendered chart. "
                    "Open in the Vega Editor at https://vega.github.io/editor."
                ),
                "path": spec_filename,
                "mediatype": "application/json",
            })

            try:
                import vl_convert as vlc
                svg_filename = f"{base}.chart.svg"
                (tmpdir / svg_filename).write_text(
                    vlc.vegalite_to_svg(chart_spec), encoding="utf-8"
                )
                resources.append({
                    "name": "chart",
                    "title": "Rendered chart (SVG)",
                    "description": "Vector-format chart rendered from the Vega-Lite specification.",
                    "path": svg_filename,
                    "mediatype": "image/svg+xml",
                })
            except Exception as exc:
                logger.warning("SVG render failed: %s", exc)

        # ── 4. Package YAML (frictionless Package, validated) ─────────────────
        geo_list_str = (
            geo_names[0] if len(geo_names) == 1
            else f"{', '.join(geo_names[:3])}{'...' if len(geo_names) > 3 else ''}"
        )
        pkg_title = title or f"{concept} ({year_str})"
        pkg_descriptor = {
            "name": base,
            "title": pkg_title,
            "description": (
                f"U.S. Census Bureau ACS 5-Year Estimates — {concept}. "
                f"Coverage: {geo_list_str}, vintage(s) {year_str}. "
                f"Universe: {universe}. Survey: {survey}. "
                f"Exported from the MORPC Census Explorer."
            ),
            "version": "1.0.0",
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "keywords": (
                ["census", "acs", "acs5", "demographics", group_code.lower()]
                + ([sumlevel.lower().replace(" ", "-")] if sumlevel else [])
            ),
            "licenses": [dict(_LICENSE)],
            "sources":  [dict(_CENSUS_SOURCE)],
            "contributors": [{**_MORPC_SOURCE, "email": "data@morpc.org", "role": "wrangler"}],
            "_concept":     concept,
            "_universe":    universe,
            "_survey":      survey,
            "_geographies": geo_names,
            "_vintages":    sorted(vintages),
            "resources":    resources,
        }

        desc_result = frictionless.Package.validate_descriptor(pkg_descriptor)
        if not desc_result.valid:
            raise ValueError(f"Package descriptor invalid: {desc_result}")

        package = frictionless.Package.from_descriptor(pkg_descriptor)
        package_filename = f"{base}.package.yaml"
        with contextlib.chdir(tmpdir):
            package.to_yaml(package_filename)
            pkg_result = frictionless.Package(package_filename).validate()
        if not pkg_result.valid:
            logger.error("Package validation failed: %s", pkg_result.stats)
            raise RuntimeError("Package validation failed after save.")

        # ── 5. README ─────────────────────────────────────────────────────────
        (tmpdir / "README.md").write_text(_README_MD, encoding="utf-8")

        # ── 6. Zip everything ─────────────────────────────────────────────────
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in sorted(tmpdir.iterdir()):
                zf.write(fp, fp.name)
        return buf.getvalue()


def export_excel(
    long_df: pd.DataFrame,
    group_code: str,
    value_mode: str = "estimate",
    show_moe: bool = False,
) -> bytes:
    """Return .xlsx bytes of the wide or percent DataFrame using ``morpc.plot.excel.ExcelChart``."""
    if ExcelChart is None:
        raise RuntimeError("morpc.plot.excel.ExcelChart is not available (morpc not importable)")

    dt = DimensionTable(long_df)
    is_pct = value_mode == "percent"
    wide = dt.percent() if is_pct else dt.wide()

    keep_vtypes = ["estimate", "moe"] if show_moe else ["estimate"]
    vtype_mask = wide.columns.get_level_values("value_type").isin(keep_vtypes)
    wide = wide.loc[:, vtype_mask]

    buf = io.BytesIO()
    ExcelChart(wide, buf, group_code[:31]).write()
    buf.seek(0)
    return buf.read()
