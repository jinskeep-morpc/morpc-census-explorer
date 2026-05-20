"""Export helpers: frictionless zip and Excel downloads."""

from __future__ import annotations

import io
import logging
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
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


def export_frictionless(
    long_df: pd.DataFrame,
    group_code: str,
    vintages: list[int],
    scope: str,
    sumlevel: str,
    chart_spec: dict | None = None,
    title: str = "",
) -> bytes:
    """Return zip bytes containing a Frictionless Data Package.

    Includes: long CSV + schema/resource YAMLs (from CensusAPI.save()),
    a datapackage.yaml descriptor, and optionally a Vega-Lite spec JSON
    and rendered SVG when chart_spec is provided.
    """
    import json
    from datetime import date
    import yaml

    vintage = sorted(vintages)[0]
    endpoint = Endpoint(SURVEY, vintage)
    group = Group(endpoint, group_code)

    with tempfile.TemporaryDirectory() as _tmp:
        tmpdir = Path(_tmp)
        api = CensusAPI(endpoint=endpoint, scope=scope, group=group, sumlevel=sumlevel)
        api.save(tmpdir)
        long_df.to_csv(tmpdir / api.filename, index=False)

        csv_name = api.filename
        schema_name = csv_name.replace(".long.csv", ".schema.yaml")
        resource_name = csv_name.replace(".long.csv", ".resource.yaml")

        resources = [
            {
                "name": "long-table",
                "path": csv_name,
                "title": "Long-form data table (all years and geographies)",
                "schema": schema_name,
            }
        ]

        if chart_spec:
            # Vega-Lite spec JSON
            spec_filename = "chart-spec.vega.json"
            (tmpdir / spec_filename).write_text(json.dumps(chart_spec, indent=2))
            resources.append({
                "name": "chart-spec",
                "path": spec_filename,
                "title": "Vega-Lite chart specification",
                "mediatype": "application/json",
            })

            # Rendered SVG via vl_convert
            try:
                import vl_convert as vlc
                svg_str = vlc.vegalite_to_svg(chart_spec)
                svg_filename = "chart.svg"
                (tmpdir / svg_filename).write_text(svg_str, encoding="utf-8")
                resources.append({
                    "name": "chart",
                    "path": svg_filename,
                    "title": "Rendered chart",
                    "mediatype": "image/svg+xml",
                })
            except Exception as exc:
                logger.warning("SVG render failed: %s", exc)

        # Build datapackage.yaml
        vintage_str = "_".join(str(v) for v in sorted(vintages))
        pkg_name = f"census-acs5-{group_code.lower()}-{vintage_str}"
        description = (
            f"U.S. Census Bureau ACS 5-Year Estimates for {group_code}, "
            f"{scope}, vintage(s) {', '.join(str(v) for v in sorted(vintages))}."
        )
        datapackage = {
            "name": pkg_name,
            "title": title or f"{group_code} ({vintage_str})",
            "description": description,
            "sources": [{
                "title": "U.S. Census Bureau, American Community Survey 5-Year Estimates",
                "path": "https://www.census.gov/data/developers/data-sets/acs-5year.html",
            }],
            "licenses": [{"name": "CC-BY-4.0", "path": "https://creativecommons.org/licenses/by/4.0/"}],
            "created": date.today().isoformat(),
            "resources": resources,
        }
        (tmpdir / "datapackage.yaml").write_text(
            yaml.dump(datapackage, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

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
