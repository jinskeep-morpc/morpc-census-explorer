"""Cache-first Census data fetching and wide-table construction."""

from __future__ import annotations

import logging

import pandas as pd
from morpc_census.api import CensusAPI, DimensionTable, Endpoint, Group, get_concept_dims_from_long
from sqlalchemy.orm import Session

from app.cache import get_census_long, put_census_long
from app.selectors import SURVEY

logger = logging.getLogger(__name__)

# Value types that can appear as columns in CensusAPI.long after the pivot.
ALL_VALUE_TYPES = ["estimate", "moe", "percent_estimate", "percent_moe", "total"]


def fetch_long_for_vintage(
    session: Session,
    group_code: str,
    vintage: int,
    scope: str,
    sumlevel: str,
) -> pd.DataFrame:
    """Return CensusAPI.long for one vintage, using the PostGIS cache when available."""
    cached = get_census_long(session, SURVEY, vintage, group_code, scope, sumlevel)
    if cached is not None:
        logger.info("Cache hit: %s %s %s %s", group_code, vintage, scope, sumlevel)
        return cached

    logger.info("Cache miss — fetching from Census API: %s %s %s %s", group_code, vintage, scope, sumlevel)
    endpoint = Endpoint(SURVEY, vintage)
    group = Group(endpoint, group_code)
    api = CensusAPI(endpoint=endpoint, scope=scope, group=group, sumlevel=sumlevel)
    long_df = api.long

    put_census_long(session, long_df, SURVEY, vintage, group_code, scope, sumlevel)
    return long_df


def fetch_all_vintages(
    session: Session,
    group_code: str,
    vintages: list[int],
    scope: str,
    sumlevel: str,
) -> pd.DataFrame:
    """Fetch and concatenate long DataFrames for all selected vintages."""
    dfs = [
        fetch_long_for_vintage(session, group_code, vintage, scope, sumlevel)
        for vintage in vintages
    ]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def fetch_all_geos(
    session: Session,
    group_code: str,
    vintages: list[int],
    geo_list: list[dict],
) -> pd.DataFrame:
    """Fetch and concatenate long DataFrames for all (scope, sumlevel) pairs and vintages."""
    frames = [
        fetch_all_vintages(session, group_code, vintages, geo["scope"], geo["sumlevel"])
        for geo in geo_list
    ]
    non_empty = [df for df in frames if not df.empty]
    return pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame()


def get_available_dims(long_df: pd.DataFrame) -> list[str]:
    """Return the dim column names DimensionTable would produce from this long DataFrame.

    Derived from the maximum number of ``!!``-delimited parts in ``variable_label``.
    """
    if long_df.empty or "variable_label" not in long_df.columns:
        return []
    max_count = long_df["variable_label"].str.count("!!").max()
    if pd.isna(max_count):
        return []
    return [f"dim_{i}" for i in range(int(max_count) + 1)]


def get_droppable_dims(long_df: pd.DataFrame) -> list[str]:
    """Return dim column names that can be dropped, requiring at least 2 dims to remain useful.

    The drop method (``summarize`` vs ``aggregate``) is chosen automatically by
    ``_choose_drop_method`` at drop time based on whether partial subtotal rows
    exist for the dim in the sibling dimensions.

    Returns an empty list when fewer than 2 dims are present, since dropping the
    only remaining dim produces an uninterpretable result.
    """
    if long_df.empty:
        return []
    try:
        dt = DimensionTable(long_df)
        cols = list(dt.dims.columns)
        return cols if len(cols) >= 2 else []
    except Exception:
        return []


def _choose_drop_method(dt: "DimensionTable", dim: str) -> str:
    """Return 'summarize' or 'aggregate' for DimensionTable.drop(dim).

    Chooses 'summarize' when the data already contains partial-subtotal rows for
    *dim* (rows where dim=="") that also carry specific values for some sibling
    dimension — meaning pre-aggregated results exist and we just need to filter.

    Chooses 'aggregate' when no such partial subtotals exist (either the dim has
    no empty rows, or the only empty rows are the grand-total row where every
    other dim is also empty, or every other dim is a "universal root" with only
    one distinct value like "Total:").
    """
    if dim not in dt.dims.columns:
        return "aggregate"
    other_dims = [d for d in dt.dims.columns if d != dim]
    subtotal_rows = dt.dims.loc[dt.dims[dim] == ""]
    if subtotal_rows.empty or not other_dims:
        return "aggregate"
    for other in other_dims:
        non_empty_in_subtotals = subtotal_rows[other][subtotal_rows[other] != ""]
        globally_non_empty = dt.dims[other][dt.dims[other] != ""]
        # A "real" sibling dim has 2+ distinct values — rules out "Total:" roots
        if len(non_empty_in_subtotals) > 0 and globally_non_empty.nunique() >= 2:
            return "summarize"
    return "aggregate"


def build_wide_table(
    long_df: pd.DataFrame,
    value_mode: str = "estimate",
    show_moe: bool = False,
    dropped_dims: list[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Pivot a long DataFrame for dash_table.DataTable with multi-level headers.

    Dim columns use the dim name as their ID (e.g. "Sex", "Age").
    Value columns use "{geoidfq}__{year}__{vtype}" as their ID.
    Column names are arrays so the table can use merge_duplicate_headers=True.

    Returns (data, columns) ready for dash_table.DataTable.
    """
    dt = DimensionTable(long_df)
    if dropped_dims:
        for dim in dropped_dims:
            method = _choose_drop_method(dt, dim)
            try:
                dt = dt.drop(dim, method=method)
            except (IndexError, ValueError, KeyError) as exc:
                logger.warning("DimensionTable.drop(%s, method=%s) failed: %s — ignoring", dim, method, exc)

    try:
        wide = dt.percent() if value_mode == "percent" else dt.wide()
    except Exception as exc:
        logger.warning("Table pivot failed (%s): %s", value_mode, exc)
        return [], []

    keep_vtypes = ["estimate", "moe"] if show_moe else ["estimate"]
    vtype_mask = wide.columns.get_level_values("value_type").isin(keep_vtypes)
    wide = wide.loc[:, vtype_mask]

    if wide.empty:
        return [], []

    dim_names = list(wide.index.names) if isinstance(wide.index, pd.MultiIndex) else [wide.index.name or "dim_0"]
    dim_name_map = get_concept_dims_from_long(long_df)
    pct_prefix = "% " if value_mode == "percent" else ""

    columns: list[dict] = []
    for dim in dim_names:
        display = dim_name_map.get(dim, dim.replace("_", " ").title())
        name_levels: list = [display, "", ""] if show_moe else [display, ""]
        columns.append({"name": name_levels, "id": dim})

    data_cols: list[tuple] = []
    for col_tup in wide.columns:
        col_map = dict(zip(wide.columns.names, col_tup))
        geo_name = col_map.get("name") or col_map.get("geoidfq", "")
        year = str(col_map.get("reference_period", ""))
        vtype = col_map.get("value_type", "")
        geoidfq = col_map.get("geoidfq") or str(len(data_cols))
        col_id = f"{geoidfq}__{year}__{vtype}"
        vtype_label = "MOE" if vtype == "moe" else "Estimate"
        name_levels = [f"{pct_prefix}{geo_name}", year, vtype_label] if show_moe else [f"{pct_prefix}{geo_name}", year]
        columns.append({"name": name_levels, "id": col_id})
        data_cols.append((col_tup, col_id))

    data: list[dict] = []
    for idx, row in wide.iterrows():
        if isinstance(idx, tuple):
            record: dict = {dim: str(val).rstrip(":").strip() for dim, val in zip(dim_names, idx)}
        else:
            record = {dim_names[0]: str(idx).rstrip(":").strip()}
        for col_tup, col_id in data_cols:
            val = row[col_tup]
            record[col_id] = round(float(val), 2) if pd.notna(val) else None
        data.append(record)

    return data, columns


def serialise_long(df: pd.DataFrame) -> dict:
    """Serialise a long DataFrame to a JSON-safe dict for dcc.Store."""
    return df.to_dict(orient="split")


def deserialise_long(store_data: dict) -> pd.DataFrame:
    """Reconstruct a long DataFrame from dcc.Store data."""
    df = pd.DataFrame(data=store_data["data"], columns=store_data["columns"])
    if "reference_period" in df.columns:
        df["reference_period"] = df["reference_period"].astype(int)
    return df
