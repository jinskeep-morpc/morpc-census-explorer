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
        for dim in dropped_dims:
            method = _choose_drop_method(dt, dim)
            try:
                dt = dt.drop(dim, method=method)
            except (IndexError, ValueError, KeyError) as exc:
                logger.warning("DimensionTable.drop(%s, method=%s) failed: %s — ignoring", dim, method, exc)
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

    # ---------------------------------------------------------------------------
    # Leaf detection and category ordering — derived from dt.dims which still
    # carries the ':' suffix that marks subtotal rows.
    # ---------------------------------------------------------------------------
    raw_dims = dt.dims  # Categorical columns; subtotal values end with ':'

    def _is_leaf_var(raw_row: pd.Series) -> bool:
        non_empty = [str(v) for v in raw_row if str(v) != ""]
        return bool(non_empty) and not non_empty[-1].endswith(":")

    display_dims_map = raw_dims.apply(
        lambda col: col.astype(str).str.rstrip(":").str.strip()
    )

    leaf_map: dict[tuple, bool] = {}
    for var_code in raw_dims.index:
        key = tuple(display_dims_map.loc[var_code])
        leaf_map[key] = leaf_map.get(key, False) or _is_leaf_var(raw_dims.loc[var_code])

    # Ordered category lists for each dim (strip ':', drop '', preserve Census order)
    dim_categories: dict[str, list[str]] = {}
    for col_name in raw_dims.columns:
        cats: list[str] = []
        for cat in raw_dims[col_name].cat.categories:
            stripped = str(cat).rstrip(":").strip()
            if stripped and stripped not in cats:
                cats.append(stripped)
        dim_categories[col_name] = cats

    # ---------------------------------------------------------------------------

    columns: list[dict] = [
        {
            "name": n,
            "id": f"__dim_{i}__",
            "categories": dim_categories.get(n, []),
        }
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
        key = tuple(str(v) for v in idx) if isinstance(idx, tuple) else (str(idx),)
        if isinstance(idx, tuple):
            record: dict = {f"__dim_{i}__": str(v) for i, v in enumerate(idx)}
        else:
            record = {"__dim_0__": str(idx)}
        record["__is_leaf__"] = leaf_map.get(key, True)
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
