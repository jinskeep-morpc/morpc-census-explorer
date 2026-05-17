"""Export helpers: frictionless zip and Excel downloads."""

from __future__ import annotations

import io
import logging
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
from morpc_census.api import DimensionTable

# morpc triggers a Census API network call on import in some environments;
# catch the failure here so the rest of the module is always importable.
try:
    from morpc.plot.excel import ExcelChart
except Exception:
    ExcelChart = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


def _frictionless_type(series: pd.Series) -> str:
    dtype = str(series.dtype)
    if "int" in dtype:
        return "integer"
    if "float" in dtype:
        return "number"
    return "string"


def export_frictionless(
    long_df: pd.DataFrame,
    group_code: str,
    vintages: list[int],
) -> bytes:
    """Return zip bytes containing long CSV, frictionless schema YAML, and resource YAML.

    Uses the ``frictionless`` package directly from the stored long DataFrame
    rather than ``CensusAPI.save()``, which requires the full API object.
    """
    import frictionless

    vintage_str = "_".join(str(v) for v in sorted(vintages))
    name = f"census-acs5-{group_code.lower()}-{vintage_str}"

    with tempfile.TemporaryDirectory() as _tmp:
        tmpdir = Path(_tmp)

        # CSV
        csv_filename = f"{name}.long.csv"
        long_df.to_csv(tmpdir / csv_filename, index=False)

        # Schema — auto-detect field types from the DataFrame
        fields = [
            {"name": col, "type": _frictionless_type(long_df[col])}
            for col in long_df.columns
        ]
        schema = frictionless.Schema.from_descriptor({"fields": fields})
        schema_filename = f"{name}.schema.yaml"
        schema.to_yaml(str(tmpdir / schema_filename))

        # Resource descriptor
        resource = frictionless.Resource(
            path=csv_filename,
            name=name,
            schema=schema,
        )
        resource_filename = f"{name}.resource.yaml"
        resource.to_yaml(str(tmpdir / resource_filename))

        # Zip all three files
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in sorted(tmpdir.iterdir()):
                zf.write(fp, fp.name)
        return buf.getvalue()


def export_excel(
    long_df: pd.DataFrame,
    group_code: str,
    value_types: list[str],
) -> bytes:
    """Return .xlsx bytes of the wide DataFrame.

    Attempts ``morpc.plot.ExcelChart`` first; falls back to plain
    ``pandas.ExcelWriter`` when morpc fails to import (morpc triggers a
    Census API network call on import that may not be available).
    """
    wide = DimensionTable(long_df).wide()

    # Filter to requested value types
    vtype_mask = wide.columns.get_level_values("value_type").isin(value_types)
    wide = wide.loc[:, vtype_mask]

    buf = io.BytesIO()
    try:
        ExcelChart(wide, buf, group_code).write()
        logger.info("Excel export via ExcelChart")
    except Exception as exc:
        logger.warning("ExcelChart unavailable (%s); falling back to pandas ExcelWriter.", exc)
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            wide.to_excel(writer, sheet_name=group_code[:31], merge_cells=True)

    buf.seek(0)
    return buf.read()
