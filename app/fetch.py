"""Cache-first Census data fetching and wide-table construction."""

from __future__ import annotations

import logging

import pandas as pd
from morpc_census.api import CensusAPI, DimensionTable, Endpoint, Group
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
    """Return dim column names that can be meaningfully dropped with ``method='summarize'``.

    A dim is droppable only when the DimensionTable contains subtotal rows for it —
    i.e. rows where that dim's value is the empty string (``''``).  Root dimensions
    (``dim_0``) are typically always populated, so they are rarely droppable.
    """
    if long_df.empty:
        return []
    try:
        dt = DimensionTable(long_df)
        if dt.dims.empty:
            return []
        return [col for col in dt.dims.columns if (dt.dims[col] == "").any()]
    except Exception:
        return []


def build_wide_table(
    long_df: pd.DataFrame,
    value_mode: str = "estimate",
    show_moe: bool = False,
    dropped_dims: list[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Pivot a long DataFrame and flatten its MultiIndex for dash_table.DataTable.

    Parameters
    ----------
    long_df:
        Concatenated output of ``CensusAPI.long`` across one or more vintages.
    value_mode:
        ``"estimate"`` uses ``DimensionTable.wide()``;
        ``"percent"`` uses ``DimensionTable.percent()``.
    show_moe:
        When True, include the MOE column alongside the primary value column.
    dropped_dims:
        List of dim column names (e.g. ``["dim_0"]``) to drop before pivoting.

    Returns
    -------
    (data, columns)
        Ready to pass directly to ``dash_table.DataTable(data=..., columns=...)``.
    """
    dt = DimensionTable(long_df)
    if dropped_dims:
        try:
            dt = dt.drop(dropped_dims)
        except (IndexError, ValueError, KeyError) as exc:
            logger.warning("DimensionTable.drop(%s) failed: %s — ignoring", dropped_dims, exc)
    is_pct = value_mode == "percent"

    try:
        wide = dt.percent() if is_pct else dt.wide()
    except Exception as exc:
        logger.warning("Table pivot failed (%s): %s", value_mode, exc)
        return [], []

    keep_vtypes = ["estimate", "moe"] if show_moe else ["estimate"]
    vtype_mask = wide.columns.get_level_values("value_type").isin(keep_vtypes)
    wide = wide.loc[:, vtype_mask]

    if wide.empty:
        return [], []

    # Resolve dimension-index names
    index = wide.index
    if isinstance(index, pd.MultiIndex):
        dim_names = list(index.names)
    else:
        dim_names = [index.name or "dim_0"]

    pct_prefix = "% " if is_pct else ""

    columns: list[dict] = [
        {"name": n.replace("_", " ").title(), "id": f"__dim_{i}__"}
        for i, n in enumerate(dim_names)
    ]
    data_cols: list[tuple[tuple, str]] = []

    for tup in wide.columns:
        col_map = dict(zip(wide.columns.names, tup))
        name = col_map.get("name") or col_map.get("geoidfq", "")
        year = col_map.get("reference_period", "")
        vtype = col_map.get("value_type", "")
        vtype_suffix = " [MOE]" if (show_moe and vtype == "moe") else ""
        label = f"{pct_prefix}{name} ({year}){vtype_suffix}"
        col_id = "__".join(str(v) for v in tup)
        columns.append({"name": label, "id": col_id})
        data_cols.append((tup, col_id))

    data: list[dict] = []
    for idx, row in wide.iterrows():
        if isinstance(idx, tuple):
            record: dict = {f"__dim_{i}__": v for i, v in enumerate(idx)}
        else:
            record = {"__dim_0__": idx}
        for tup, col_id in data_cols:
            val = row[tup]
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
