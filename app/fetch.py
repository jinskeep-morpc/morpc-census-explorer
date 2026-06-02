"""Cache-first Census data fetching and wide-table construction."""

from __future__ import annotations

import logging

import pandas as pd
from morpc_census.api import CensusAPI, DimensionTable, Endpoint, Group
from sqlalchemy.orm import Session

from app.cache import get_census_long, put_census_long
from app.selectors import SURVEY, vintage_group_code  # kept for backward compat; not used directly below

logger = logging.getLogger(__name__)

# Value types that can appear as columns in CensusAPI.long after the pivot.
ALL_VALUE_TYPES = ["estimate", "moe", "percent_estimate", "percent_moe", "total"]


def _estimate_col(long_df: pd.DataFrame) -> str:
    """Return the column that holds the primary count/estimate value.

    ACS surveys use ``estimate``; decennial surveys produce ``total``
    (their variables carry no value-type suffix).  Checks for non-null values
    because the DB cache stores all value-type columns, so ``estimate`` may be
    present but entirely null when the survey only produced ``total``.
    """
    if "estimate" in long_df.columns and long_df["estimate"].notna().any():
        return "estimate"
    if "total" in long_df.columns and long_df["total"].notna().any():
        return "total"
    # Fallback: prefer estimate for column naming consistency
    return "estimate" if "estimate" in long_df.columns else "total"


def fetch_long_for_vintage(
    session: Session,
    group_code: str,
    vintage: int,
    scope: str,
    sumlevel: str,
    survey: str = "acs/acs5",
) -> pd.DataFrame:
    """Return CensusAPI.long for one vintage, using the PostGIS cache when available.

    *group_code* is always the canonical code (e.g. ``P1`` for dec/pl across
    all vintages).  The cache is keyed on this canonical code so that data
    fetched for different vintages of the same table shares one cache entry key.
    The vintage-specific API code (e.g. ``PL001`` for dec/pl 2000) is derived
    at fetch time and never exposed to callers.
    """
    cached = get_census_long(session, survey, vintage, group_code, scope, sumlevel)
    if cached is not None:
        logger.info("Cache hit: %s %s %s %s", group_code, vintage, scope, sumlevel)
        return cached

    # Translate canonical code → the code the Census API actually uses for this vintage
    api_group_code = vintage_group_code(group_code, survey, vintage)
    logger.info(
        "Cache miss — fetching from Census API: %s (api=%s) %s %s %s",
        group_code, api_group_code, vintage, scope, sumlevel,
    )
    endpoint = Endpoint(survey, vintage)
    group = Group(endpoint, api_group_code)
    api = CensusAPI(endpoint=endpoint, scope=scope, group=group, sumlevel=sumlevel)
    long_df = api.long

    # Store under the canonical cache key
    put_census_long(session, long_df, survey, vintage, group_code, scope, sumlevel)
    return long_df


def fetch_all_vintages(
    session: Session,
    group_code: str,
    vintages: list[int],
    scope: str,
    sumlevel: str,
    survey: str = "acs/acs5",
) -> pd.DataFrame:
    """Fetch and concatenate long DataFrames for all selected vintages."""
    dfs = [
        fetch_long_for_vintage(session, group_code, vintage, scope, sumlevel, survey)
        for vintage in vintages
    ]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def fetch_all_geos(
    session: Session,
    group_code: str,
    vintages: list[int],
    geo_list: list[dict],
    survey: str = "acs/acs5",
) -> pd.DataFrame:
    """Fetch and concatenate long DataFrames for all (scope, sumlevel) pairs and vintages."""
    frames = [
        fetch_all_vintages(session, group_code, vintages, geo["scope"], geo["sumlevel"], survey)
        for geo in geo_list
    ]
    non_empty = [df for df in frames if not df.empty]
    return pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame()


def get_available_dims(long_df: pd.DataFrame) -> list[str]:
    """Return the dim column names DimensionTable produces from this long DataFrame."""
    if long_df.empty or "variable_label" not in long_df.columns:
        return []
    try:
        return list(DimensionTable(long_df).dims.columns)
    except Exception:
        return []


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



def _apply_dim_filters_to_wide(
    wide: "pd.DataFrame",
    dim_filters: "dict[str, list[str]] | None",
) -> "pd.DataFrame":
    """Filter rows of a wide DataFrame by its dim index."""
    if not dim_filters:
        return wide
    index = wide.index
    if isinstance(index, pd.MultiIndex):
        mask = pd.Series(True, index=range(len(wide)))
        for dim_name, vals in dim_filters.items():
            if dim_name in index.names and vals:
                mask &= index.get_level_values(dim_name).astype(str).isin(
                    [str(v) for v in vals]
                )
        return wide.iloc[mask.values]
    else:
        if index.name and index.name in dim_filters:
            vals = dim_filters[index.name]
            if vals:
                return wide.loc[index.astype(str).isin([str(v) for v in vals])]
    return wide


def build_table_df(
    long_df: pd.DataFrame,
    value_mode: str = "estimate",
    show_moe: bool = False,
    dropped_dims: list[str] | None = None,
    dim_filters: dict[str, list[str]] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Build (data, columns) for a Dash DataTable from CensusAPI.long.

    Calls DimensionTable.wide() or percent() directly — no leaf filtering.
    Column headers use 2 levels: geo name (top, merged) and year label (bottom).
    Dim index values become the leftmost row-header columns.
    """
    if long_df.empty or "variable_label" not in long_df.columns:
        return [], []

    dt = DimensionTable(long_df)
    if dropped_dims:
        for dim in dropped_dims:
            try:
                dt = dt.drop(dim)
            except (IndexError, ValueError, KeyError) as exc:
                logger.warning("DimensionTable.drop(%s) failed: %s — ignoring", dim, exc)

    is_pct = value_mode == "percent"
    try:
        wide = dt.percent() if is_pct else dt.wide()
    except Exception as exc:
        logger.warning("Table pivot failed (%s): %s", value_mode, exc)
        return [], []

    # Filter value_type columns — decennial data uses "total" instead of "estimate"
    est_col = _estimate_col(long_df)
    keep_vtypes = [est_col, "moe"] if show_moe else [est_col]
    vtype_mask = wide.columns.get_level_values("value_type").isin(keep_vtypes)
    wide = wide.loc[:, vtype_mask]
    if wide.empty:
        return [], []

    # Apply dim filters to the row index
    if dim_filters:
        wide = _apply_dim_filters_to_wide(wide, dim_filters)
    if wide.empty:
        return [], []

    # Extract dim names from index
    if isinstance(wide.index, pd.MultiIndex):
        dim_names = list(wide.index.names)
    else:
        dim_names = [wide.index.name or "dim_0"]

    # Build columns spec — 2-level names for merge_duplicate_headers=True
    # Dim cols: ["", dim_name] — blank top level, dim name at bottom
    dim_col_specs = [
        {"name": ["", dn], "id": f"__dim_{dn}__"}
        for dn in dim_names
    ]

    # Data cols: [geo_name, year_label] — year_label includes [MOE] suffix for moe columns
    data_col_specs = []
    for tup in wide.columns:
        col_map = dict(zip(wide.columns.names, tup))
        geo_name = col_map.get("name", "")
        year = col_map.get("reference_period", "")
        vtype = col_map.get("value_type", "")
        geoidfq = col_map.get("geoidfq", "")
        year_label = f"{year} [MOE]" if vtype == "moe" else str(year)
        col_id = f"{geoidfq}__{year}__{vtype}"
        data_col_specs.append({"name": [geo_name, year_label], "id": col_id, "_tup": tup})

    columns = dim_col_specs + [{"name": s["name"], "id": s["id"]} for s in data_col_specs]

    # Build data records
    data = []
    for row_idx, row in wide.iterrows():
        idx_vals = row_idx if isinstance(row_idx, tuple) else (row_idx,)
        record = {f"__dim_{dim_names[i]}__": str(v) for i, v in enumerate(idx_vals)}
        for spec in data_col_specs:
            val = row[spec["_tup"]]
            record[spec["id"]] = round(float(val), 2) if pd.notna(val) else None
        data.append(record)

    return data, columns


def build_chart_df(
    long_df: pd.DataFrame,
    dropped_dims: list[str] | None = None,
    value_mode: str = "estimate",
) -> pd.DataFrame:
    """Build a long DataFrame for charting by joining DimensionTable dims to long data.

    Returns columns: [dim_cols..., 'name', 'reference_period', 'estimate'].
    Dim columns are ordered Categorical. Subtotal rows (any dim is '') are excluded.
    When value_mode='percent', estimates are expressed as a percentage of the grand total
    per geography and vintage.
    """
    if long_df.empty or "variable_label" not in long_df.columns:
        return pd.DataFrame()

    dt = DimensionTable(long_df)
    if dropped_dims:
        for dim in dropped_dims:
            try:
                dt = dt.drop(dim)
            except (IndexError, ValueError, KeyError) as exc:
                logger.warning("DimensionTable.drop(%s) failed: %s — ignoring", dim, exc)

    est_col = _estimate_col(long_df)

    long_copy = dt.long.copy()
    for col in dt.dims.columns:
        clean = dt.dims[col].astype(str)
        raw_cats = list(dt.dims[col].cat.categories)
        cats = list(dict.fromkeys(str(v) for v in raw_cats))
        long_copy[col] = long_copy["variable"].map(clean).fillna("")
        long_copy[col] = pd.Categorical(long_copy[col], categories=cats, ordered=True)

    dim_cols = list(dt.dims.columns)

    # Drop subtotal rows — rows where any dim column is "" have no meaningful
    # label for that dimension and would appear as blank entries on chart axes.
    if dim_cols:
        mask = pd.concat(
            [long_copy[col].astype(str) != "" for col in dim_cols], axis=1
        ).all(axis=1)
        long_copy = long_copy[mask]

    if value_mode == "percent" and len(dt.dims.columns) > 0:
        # Grand total: the variable(s) where all dims after the first are "".
        total_mask = (dt.dims.iloc[:, 1:] == "").all(axis=1) if len(dt.dims.columns) > 1 else pd.Series(True, index=dt.dims.index)
        total_vars = set(dt.dims.index[total_mask])
        if total_vars:
            totals = (
                dt.long[dt.long["variable"].isin(total_vars)]
                .groupby(["geoidfq", "reference_period"], observed=True)
                .first()[[est_col]]
                .rename(columns={est_col: "_total"})
                .reset_index()
            )
            long_copy = long_copy.merge(totals, on=["geoidfq", "reference_period"], how="left")
            long_copy[est_col] = (long_copy[est_col] / long_copy["_total"] * 100).round(2)
            long_copy = long_copy.drop(columns=["_total"])

    keep = dim_cols + ["name", "reference_period", est_col]
    keep = [c for c in keep if c in long_copy.columns]
    result = long_copy[keep].reset_index(drop=True)
    # Normalize to "estimate" so downstream callers don't need to know the survey type.
    if est_col != "estimate":
        result = result.rename(columns={est_col: "estimate"})

    # Convert reference_period to an ordered Categorical of strings so Vega-Lite
    # treats year as ordinal ("O") rather than quantitative ("Q"). This ensures
    # only the fetched years appear on the axis with no numeric interpolation.
    if "reference_period" in result.columns:
        years = sorted(result["reference_period"].dropna().unique())
        result["reference_period"] = pd.Categorical(
            result["reference_period"].astype(str),
            categories=[str(y) for y in years],
            ordered=True,
        )

    return result


def serialise_long(df: pd.DataFrame) -> dict:
    """Serialise a long DataFrame to a JSON-safe dict for dcc.Store."""
    return df.to_dict(orient="split")


def deserialise_long(store_data: dict) -> pd.DataFrame:
    """Reconstruct a long DataFrame from dcc.Store data."""
    df = pd.DataFrame(data=store_data["data"], columns=store_data["columns"])
    if "reference_period" in df.columns:
        df["reference_period"] = df["reference_period"].astype(int)
    return df
