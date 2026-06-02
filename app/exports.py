"""Export helpers: frictionless zip and Excel downloads."""

from __future__ import annotations

import io
import logging
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import yaml as _yaml


class _NoAliasDumper(_yaml.SafeDumper):
    """SafeDumper that never emits anchors or aliases."""
    def ignore_aliases(self, data):
        return True


def _yaml_dump(obj: object) -> str:
    return _yaml.dump(obj, Dumper=_NoAliasDumper, default_flow_style=False,
                      allow_unicode=True, sort_keys=False)
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


def _long_resource_entry(
    long_df: pd.DataFrame,
    csv_name: str,
    schema_name: str,
    group_code: str,
    vintages: list[int],
    scope: str,
) -> dict:
    """Build a datapackage resource entry dict for the raw long CSV."""
    concept  = str(long_df["concept"].dropna().iloc[0])  if "concept"  in long_df.columns else group_code
    universe = str(long_df["universe"].dropna().iloc[0]) if "universe" in long_df.columns else ""
    survey   = str(long_df["survey"].dropna().iloc[0])   if "survey"   in long_df.columns else SURVEY
    year_str = ", ".join(str(v) for v in sorted(vintages))

    title = f"{concept} — raw long-form data ({year_str})"
    description = (
        f"Raw long-format Census data for {concept} from {survey} ({year_str}), "
        f"{scope}. Each row is one variable for one geography. "
        f"Universe: {universe}."
    )

    return {
        "name": "long-data",
        "title": title,
        "description": description,
        "path": csv_name,
        "schema": schema_name,
        "mediatype": "text/csv",
        "sources": [_CENSUS_SOURCE],
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

    The package includes:

    All files share the same base name as CensusAPI produces, e.g.
    ``census-acs-acs5-2023-county-franklin-b01001``:

    - ``{base}.long.csv`` / ``.long.schema.yaml`` / ``.long.resource.yaml``
    - ``{base}.table.csv`` / ``.table.schema.yaml`` / ``.table.resource.yaml``
    - ``{base}.chart.vega.json`` / ``.chart.svg`` (when chart_spec given)
    - ``{base}.package.yaml`` — Frictionless Data Package descriptor
    """
    import json

    vintage = sorted(vintages)[0]
    endpoint = Endpoint(SURVEY, vintage)
    group = Group(endpoint, group_code)
    year_str = ", ".join(str(v) for v in sorted(vintages))

    with tempfile.TemporaryDirectory() as _tmp:
        tmpdir = Path(_tmp)

        # ── 1. Raw long-form data ────────────────────────────────────────────
        api = CensusAPI(endpoint=endpoint, scope=scope, group=group, sumlevel=sumlevel)
        api.save(tmpdir)
        # Overwrite the stub CSV with the actual (possibly multi-vintage) data
        long_df.to_csv(tmpdir / api.filename, index=False)

        # Use api.name as the shared base for every file in the package
        # (e.g. "census-acs-acs5-2023-county-franklin-b01001")
        base = api.name

        # api.save() writes {base}.schema.yaml / {base}.resource.yaml (no .long. infix).
        # Rename them to {base}.long.schema.yaml / {base}.long.resource.yaml so every
        # file in the package carries a consistent infix that matches .long.csv.
        old_schema_path   = tmpdir / f"{base}.schema.yaml"
        old_resource_path = tmpdir / f"{base}.resource.yaml"

        long_csv_name    = f"{base}.long.csv"
        long_schema_name = f"{base}.long.schema.yaml"
        long_res_name    = f"{base}.long.resource.yaml"

        old_schema_path.rename(tmpdir / long_schema_name)

        # Patch the schema reference inside the resource YAML before renaming it
        res_raw = _yaml.safe_load(old_resource_path.read_text(encoding="utf-8"))
        res_raw["schema"] = long_schema_name
        (tmpdir / long_res_name).write_text(_yaml_dump(res_raw), encoding="utf-8")
        old_resource_path.unlink()

        # ── 2. Dimension table ───────────────────────────────────────────────
        dt = _apply_drops(long_df, dropped_dims)
        table_name = f"{base}.table"      # DimensionTable.save() appends .csv / .schema.yaml / .resource.yaml

        concept  = str(long_df["concept"].dropna().iloc[0])  if "concept"  in long_df.columns else group_code
        universe = str(long_df["universe"].dropna().iloc[0]) if "universe" in long_df.columns else ""
        survey   = str(long_df["survey"].dropna().iloc[0])   if "survey"   in long_df.columns else SURVEY

        if "name" in long_df.columns:
            geo_names = sorted(long_df["name"].dropna().unique().tolist())
        else:
            geo_names = sorted(long_df["geoidfq"].dropna().unique().tolist())

        geo_summary = (
            geo_names[0] if len(geo_names) == 1
            else f"{len(geo_names)} geographies"
        )
        dropped_note = (
            f" Dimensions collapsed: {', '.join(dropped_dims)}."
            if dropped_dims else ""
        )
        table_description = (
            f"Dimension table for {concept} from {survey} ({year_str}), "
            f"{geo_summary}.{dropped_note} Universe: {universe}."
        )

        table_title = title or f"{concept} — dimension table ({year_str})"

        dt.save(
            tmpdir,
            table_name,
            value_mode=value_mode,
            title=table_title,
            description=table_description,
        )

        table_csv_name    = f"{table_name}.csv"
        table_schema_name = f"{table_name}.schema.yaml"
        table_res_name    = f"{table_name}.resource.yaml"

        # ── 3. Chart artifacts ───────────────────────────────────────────────
        resources = []

        # Long data resource
        resources.append(_long_resource_entry(long_df, long_csv_name, long_schema_name, group_code, vintages, scope))

        # Dimension table resource — read back from the written YAML for consistency
        resources.append({
            "name": "dimension-table",
            "title": table_title,
            "description": table_description,
            "path": table_csv_name,
            "schema": table_schema_name,
            "mediatype": "text/csv",
            "_concept":  concept,
            "_universe": universe,
            "_survey":   survey,
            "_geographies": geo_names,
            "_vintages": sorted(vintages),
            "_value_mode": value_mode,
            "_dimensions_dropped": list(dropped_dims or []),
        })

        if chart_spec:
            spec_filename = f"{base}.chart.vega.json"
            (tmpdir / spec_filename).write_text(json.dumps(chart_spec, indent=2), encoding="utf-8")
            resources.append({
                "name": "chart-spec",
                "title": "Vega-Lite chart specification",
                "description": "Vega-Lite JSON specification for the rendered chart. "
                               "Open in the Vega Editor at https://vega.github.io/editor.",
                "path": spec_filename,
                "mediatype": "application/json",
            })

            try:
                import vl_convert as vlc
                svg_str = vlc.vegalite_to_svg(chart_spec)
                svg_filename = f"{base}.chart.svg"
                (tmpdir / svg_filename).write_text(svg_str, encoding="utf-8")
                resources.append({
                    "name": "chart",
                    "title": "Rendered chart (SVG)",
                    "description": "Vector-format chart rendered from the Vega-Lite specification.",
                    "path": svg_filename,
                    "mediatype": "image/svg+xml",
                })
            except Exception as exc:
                logger.warning("SVG render failed: %s", exc)

        # ── 4. datapackage.yaml ───────────────────────────────────────────────
        pkg_name = base
        geo_list_str = (
            geo_names[0] if len(geo_names) == 1
            else f"{', '.join(geo_names[:3])}{'...' if len(geo_names) > 3 else ''}"
        )
        pkg_title = title or f"{concept} ({year_str})"
        pkg_description = (
            f"U.S. Census Bureau ACS 5-Year Estimates — {concept}. "
            f"Coverage: {geo_list_str}, vintage(s) {year_str}. "
            f"Universe: {universe}. "
            f"Survey: {survey}. "
            f"Exported from the MORPC Census Explorer."
        )

        keywords = ["census", "acs", "acs5", "demographics", group_code.lower()]
        if sumlevel:
            keywords.append(sumlevel.lower().replace(" ", "-"))

        datapackage = {
            "name": pkg_name,
            "title": pkg_title,
            "description": pkg_description,
            "version": "1.0.0",
            "created": date.today().isoformat(),
            "keywords": keywords,
            "licenses": [_LICENSE],
            "sources":  [_CENSUS_SOURCE],
            "contributors": [
                {**_MORPC_SOURCE, "email": "data@morpc.org", "role": "wrangler"},
            ],
            "_concept":  concept,
            "_universe": universe,
            "_survey":   survey,
            "_geographies": geo_names,
            "_vintages": sorted(vintages),
            "resources": resources,
        }

        package_filename = f"{base}.package.yaml"
        (tmpdir / package_filename).write_text(_yaml_dump(datapackage), encoding="utf-8")

        # ── 5. Zip everything ────────────────────────────────────────────────
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
