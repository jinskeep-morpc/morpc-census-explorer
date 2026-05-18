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
) -> bytes:
    """Return zip bytes containing long CSV, frictionless schema YAML, and resource YAML.

    Uses ``CensusAPI.save()`` to generate rich frictionless metadata for the
    earliest selected vintage, then overwrites the CSV with the (potentially
    multi-vintage) ``long_df``.
    """
    vintage = sorted(vintages)[0]
    endpoint = Endpoint(SURVEY, vintage)
    group = Group(endpoint, group_code)

    with tempfile.TemporaryDirectory() as _tmp:
        tmpdir = Path(_tmp)
        api = CensusAPI(endpoint=endpoint, scope=scope, group=group, sumlevel=sumlevel)
        api.save(tmpdir)
        # Overwrite single-vintage CSV with combined multi-vintage data
        long_df.to_csv(tmpdir / api.filename, index=False)

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

    primary_vtype = "percent_estimate" if is_pct else "estimate"
    moe_vtype = "percent_moe" if is_pct else "moe"
    keep_vtypes = [primary_vtype, moe_vtype] if show_moe else [primary_vtype]
    vtype_mask = wide.columns.get_level_values("value_type").isin(keep_vtypes)
    wide = wide.loc[:, vtype_mask]

    buf = io.BytesIO()
    ExcelChart(wide, buf, group_code[:31]).write()
    buf.seek(0)
    return buf.read()
