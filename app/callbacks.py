"""Dash callback registration for morpc-census-explorer."""

from __future__ import annotations

import logging

import altair as alt
import pandas as pd

import dash
from dash import ALL, Input, Output, State, dash_table, dcc, html, no_update

logger = logging.getLogger(__name__)

import dash_bootstrap_components as dbc

from app.db import SessionLocal
from app.exports import export_excel, export_frictionless
from app.fetch import (
    build_wide_table,
    deserialise_long,
    fetch_all_geos,
    get_droppable_dims,
    serialise_long,
)
from morpc_census.api import get_concept_dims_from_long
from app.selectors import group_options_for_topic


# ---------------------------------------------------------------------------
# Pure callback logic — testable without a running Dash server
# ---------------------------------------------------------------------------

def compute_group_options(topic_code: str | None) -> tuple[list, None, bool]:
    """Return (options, value, disabled) for the group dropdown."""
    if not topic_code:
        return [], None, True
    options = group_options_for_topic(topic_code)
    return options, None, False


def compute_fetch_button_disabled(
    topic: str | None,
    group: str | None,
    vintages: list | None,
    geo_list: list | None,
) -> bool:
    """Return True (disabled) unless topic, group, vintages, and ≥1 geography are set."""
    return not all([topic, group, vintages]) or not geo_list


def _friendly_error(exc: Exception) -> str:
    """Return a concise, user-facing error message from an exception."""
    name = type(exc).__name__
    msg = str(exc)
    if "OperationalError" in name or "connection" in msg.lower():
        return "Database connection failed. Is the DB service running?"
    if "Timeout" in name or "timeout" in msg.lower():
        return "Census API request timed out. Try again in a moment."
    if "KeyError" in name:
        return f"Unexpected data format ({msg}). The Census API response may have changed."
    return f"{name}: {msg}"


def compute_fetch_and_store(
    n_clicks: int | None,
    group_code: str,
    vintages: list[int],
    geo_list: list[dict],
) -> tuple[dict | None, str, str, bool]:
    """Fetch all vintages/geographies and return serialised long DataFrame + status message.

    Returns (store_data, status_text, error_message, error_is_open).
    """
    session = None
    try:
        session = SessionLocal()
        long_df = fetch_all_geos(session, group_code, vintages, geo_list)
        if long_df.empty:
            return no_update, "", "No data returned for the selected combination.", True
        row_count = len(long_df)
        return serialise_long(long_df), f"Loaded {row_count:,} rows for {group_code}.", "", False
    except Exception as exc:
        logger.exception("Fetch failed for group=%s vintages=%s", group_code, vintages)
        return no_update, "", _friendly_error(exc), True
    finally:
        if session is not None:
            session.close()


def compute_table(
    store_data: dict | None,
    value_mode: str | None,
    show_moe: bool | None,
    dropped_dims: list[str] | None = None,
) -> tuple[list, list, dict]:
    """Build DataTable data/columns from stored long DataFrame.

    Returns (data, columns, value_type_card_style).
    """
    if not store_data:
        return [], [], {"display": "none"}

    long_df = deserialise_long(store_data)
    data, columns = build_wide_table(long_df, value_mode or "estimate", bool(show_moe), dropped_dims)
    return data, columns, {"display": "block"}


def compute_dim_controls(
    store_data: dict | None,
    dropped_dims: list[str] | None,
) -> tuple[list, dict]:
    """Return (drop_buttons, reset_btn_style) for the dimension controls bar."""
    if not store_data:
        return [], {"display": "none"}
    long_df = deserialise_long(store_data)
    droppable = get_droppable_dims(long_df)
    if not droppable:
        return [], {"display": "none"}
    dropped = set(dropped_dims or [])
    dim_name_map = get_concept_dims_from_long(long_df)
    buttons = [
        dbc.Button(
            f"Drop {dim_name_map.get(dim, dim.replace('_', ' ').title())}",
            id={"type": "drop-dim-btn", "index": dim},
            size="sm",
            color="warning",
            outline=True,
            n_clicks=0,
            className="me-2",
        )
        for dim in droppable
        if dim not in dropped
    ]
    reset_style = {"display": "inline-block"} if dropped else {"display": "none"}
    return buttons, reset_style


def compute_wide_data(
    store_data: dict | None,
    value_mode: str | None,
    show_moe: bool | None,
    dropped_dims: list[str] | None = None,
) -> dict | None:
    """Build the unfiltered wide table. Returns ``{"data": [...], "columns": [...]}`` or None."""
    if not store_data:
        return None
    long_df = deserialise_long(store_data)
    data, columns = build_wide_table(long_df, value_mode or "estimate", bool(show_moe), dropped_dims)
    if not data:
        return None
    return {"data": data, "columns": columns}


def compute_dim_filter_controls(wide_data: dict | None) -> list:
    """Return a Dropdown for each dim column that has more than one unique value."""
    if not wide_data:
        return []
    data = wide_data.get("data", [])
    columns = wide_data.get("columns", [])
    dim_cols = [c for c in columns if c["id"].startswith("__dim_")]
    if not dim_cols:
        return []
    controls = []
    for col in dim_cols:
        col_id = col["id"]       # "__dim_0__"
        col_name = col_id[2:-2]  # "dim_0"
        present = {str(row[col_id]) for row in data if row.get(col_id) not in (None, "")}
        ordered_cats = col.get("categories", [])
        if ordered_cats:
            unique_vals = [c for c in ordered_cats if c in present]
        else:
            unique_vals = sorted(present)
        if len(unique_vals) <= 1:
            continue
        controls.append(
            html.Span(
                [
                    dbc.Label(col["name"], className="small me-1 mb-0 fw-semibold"),
                    dcc.Dropdown(
                        id={"type": "dim-filter", "index": col_name},
                        options=[{"label": v, "value": v} for v in unique_vals],
                        value=None,
                        multi=True,
                        placeholder="All…",
                        style={"minWidth": "180px"},
                    ),
                ],
                className="d-inline-flex align-items-center gap-1 me-3",
            )
        )
    return controls


def apply_dim_filters(
    wide_data: dict | None,
    filters: dict[str, list],
) -> tuple[list[dict], list[dict]]:
    """Filter wide table rows by dim column selections.

    Parameters
    ----------
    wide_data:
        Dict from ``compute_wide_data`` with ``"data"`` and ``"columns"`` keys.
    filters:
        ``{dim_name: [selected_values]}`` — only dims with non-empty selections applied.
    """
    if not wide_data:
        return [], []
    data = list(wide_data.get("data", []))
    columns = list(wide_data.get("columns", []))
    for dim_name, selected_vals in (filters or {}).items():
        if selected_vals:
            col_id = f"__{dim_name}__"
            data = [row for row in data if row.get(col_id) in selected_vals]
    return data, columns


def compute_dropped_dims(
    n_drops: list[int | None],
    n_reset: int | None,
    current_dropped: list[str] | None,
    trigger_id,
) -> list[str]:
    """Return updated dropped-dims list after a drop or reset action."""
    current = list(current_dropped or [])
    if trigger_id == "long-data-store":
        return []
    if trigger_id == "reset-dims-btn":
        return []
    if isinstance(trigger_id, dict) and trigger_id.get("type") == "drop-dim-btn":
        dim = trigger_id["index"]
        if dim not in current:
            return current + [dim]
    return current


def compute_geo_list(
    n_add: int | None,
    n_removes: list[int | None],
    scope: str | None,
    sumlevel: str | None,
    current_list: list | None,
    trigger_id=None,
) -> list[dict]:
    """Return updated geography list after an add or individual remove action.

    ``trigger_id`` is the Dash ctx.triggered_id value; callers pass it
    explicitly so the function is testable outside a Dash callback context.
    """
    current = current_list or []

    if trigger_id == "add-geo-btn":
        if scope and sumlevel:
            new_geo = {"scope": scope, "sumlevel": sumlevel}
            if new_geo not in current:
                return current + [new_geo]
        return current

    if isinstance(trigger_id, dict) and trigger_id.get("type") == "remove-geo":
        idx = trigger_id["index"]
        return [g for i, g in enumerate(current) if i != idx]

    return current


def compute_geo_chips(geo_list: list | None) -> list:
    """Return inline badge+button elements for each geography in the list."""
    if not geo_list:
        return [
            html.Small(
                "No geographies added. Select a scope and summary level above, then click Add Geography.",
                className="text-muted",
            )
        ]
    chips = []
    for i, geo in enumerate(geo_list):
        chips.append(
            html.Span(
                [
                    dbc.Badge(
                        f"{geo['scope']} / {geo['sumlevel']}",
                        color="primary",
                        pill=True,
                    ),
                    html.Button(
                        "×",
                        id={"type": "remove-geo", "index": i},
                        n_clicks=0,
                        className="btn btn-link btn-sm p-0 ms-1 text-danger",
                        style={"lineHeight": "1", "verticalAlign": "middle"},
                    ),
                ],
                className="me-2 d-inline-flex align-items-center",
            )
        )
    return chips


def compute_frictionless_download(
    store_data: dict | None,
    group_code: str | None,
    vintages: list[int] | None,
    geo_list: list[dict] | None,
) -> dict | None:
    """Return dcc.send_bytes payload for frictionless zip, or None on error."""
    if not store_data or not group_code or not vintages or not geo_list:
        return no_update
    try:
        long_df = deserialise_long(store_data)
        scope = geo_list[0]["scope"]
        sumlevel = geo_list[0]["sumlevel"]
        zip_bytes = export_frictionless(long_df, group_code, vintages, scope, sumlevel)
        vintage_str = "_".join(str(v) for v in sorted(vintages))
        filename = f"census-acs5-{group_code.lower()}-{vintage_str}.zip"
        return dcc.send_bytes(zip_bytes, filename)
    except Exception as exc:
        logger.error("Frictionless export failed: %s", exc)
        return no_update


def compute_excel_download(
    store_data: dict | None,
    group_code: str | None,
    vintages: list[int] | None,
    value_mode: str | None,
    show_moe: bool | None,
) -> dict | None:
    """Return dcc.send_bytes payload for Excel .xlsx, or no_update on error."""
    if not store_data or not group_code:
        return no_update
    try:
        long_df = deserialise_long(store_data)
        xlsx_bytes = export_excel(long_df, group_code, value_mode or "estimate", bool(show_moe))
        vintage_str = "_".join(str(v) for v in sorted(vintages or []))
        filename = f"census-acs5-{group_code.lower()}-{vintage_str}.xlsx"
        return dcc.send_bytes(xlsx_bytes, filename)
    except Exception as exc:
        logger.error("Excel export failed: %s", exc)
        return no_update


def wide_to_long(data: list[dict], columns: list[dict]) -> pd.DataFrame:
    """Convert build_wide_table output to a long DataFrame for charting.

    Returns a DataFrame with columns:
    - ``dim_0``, ``dim_1``, ... : ordered Categorical per dimension level
    - ``geography``: geo name parsed from the value column ID
    - ``year``: vintage year parsed from the value column ID
    - ``value``: numeric estimate value

    Subtotal/aggregate rows are excluded using the ``__is_leaf__`` flag written
    by ``build_wide_table``, with a fallback heuristic for older data.
    """
    df_wide = pd.DataFrame(data)
    dim_cols = sorted(
        [c for c in columns if c["id"].startswith("__dim_")],
        key=lambda c: c["id"],
    )
    est_cols = [c for c in columns if not c["id"].startswith("__dim_") and "[MOE]" not in c["name"]]

    if df_wide.empty or not est_cols:
        return pd.DataFrame()

    # Filter to leaf rows only
    if "__is_leaf__" in df_wide.columns:
        df_wide = df_wide[df_wide["__is_leaf__"]].reset_index(drop=True)
    else:
        # Fallback: heuristic for data written before __is_leaf__ was added
        dim_col_ids = [c["id"] for c in dim_cols]
        if len(dim_col_ids) > 1:
            higher_ids = dim_col_ids[1:]

            def _is_total(row: pd.Series) -> bool:
                return all(
                    row.get(cid) in (None, "", "nan", "None") or pd.isna(row.get(cid))
                    for cid in higher_ids
                )

            df_wide = df_wide[~df_wide.apply(_is_total, axis=1)].reset_index(drop=True)

    if df_wide.empty:
        return pd.DataFrame()

    dim_col_ids = [c["id"] for c in dim_cols]
    dim_rename = {c["id"]: c["id"].strip("_") for c in dim_cols}  # __dim_0__ → dim_0

    frames = []
    for col in est_cols:
        parts = col["id"].rsplit("__", 3)
        geography = parts[0] if len(parts) == 4 else col["name"]
        year = int(parts[1]) if len(parts) == 4 and parts[1].isdigit() else None

        chunk = df_wide[dim_col_ids + [col["id"]]].copy()
        chunk = chunk.rename(columns={**dim_rename, col["id"]: "value"})
        chunk["geography"] = geography
        chunk["year"] = year
        frames.append(chunk)

    long_df = pd.concat(frames, ignore_index=True).dropna(subset=["value"])

    # Apply ordered Categorical dtype to each dim column using Census-defined order
    for dc in dim_cols:
        clean_name = dc["id"].strip("_")  # dim_0, dim_1, ...
        cats = dc.get("categories", [])
        if clean_name in long_df.columns and cats:
            long_df[clean_name] = pd.Categorical(
                long_df[clean_name], categories=cats, ordered=True
            )

    return long_df


def _chart_axis_options(wide_data: dict) -> list[dict]:
    """Return dropdown options derived from wide_data columns."""
    columns = wide_data.get("columns", [])
    dim_cols = sorted(
        [c for c in columns if c["id"].startswith("__dim_")],
        key=lambda c: c["id"],
    )
    options = [{"label": c["name"], "value": c["id"].strip("_")} for c in dim_cols]
    options += [
        {"label": "Geography", "value": "geography"},
        {"label": "Year", "value": "year"},
        {"label": "Value", "value": "value"},
    ]
    return options


def render_chart_image(
    long_df: pd.DataFrame,
    x_col: str,
    y_col: str,
    color_col: str,
    chart_type: str,
) -> dict:
    """Return a Vega-Lite spec dict from long-format data, or {} on error."""
    try:
        df = long_df.copy()
        if "reference_period" in df.columns:
            df["reference_period"] = df["reference_period"].astype(str)

        x_enc = alt.X(f"{x_col}:N", title=x_col.replace("_", " ").title())
        y_enc = alt.Y(f"{y_col}:Q", title=y_col.replace("_", " ").title())
        color_enc = alt.Color(f"{color_col}:N", title="")
        tooltip = [f"{x_col}:N", f"{color_col}:N", f"{y_col}:Q"]

        if chart_type == "bar":
            chart = (
                alt.Chart(df)
                .mark_bar()
                .encode(x=x_enc, xOffset=color_enc, y=y_enc, color=color_enc, tooltip=tooltip)
            )
        elif chart_type == "line":
            chart = (
                alt.Chart(df)
                .mark_line(point=True)
                .encode(x=x_enc, y=y_enc, color=color_enc, tooltip=tooltip)
            )
        else:
            chart = (
                alt.Chart(df)
                .mark_point()
                .encode(x=x_enc, y=y_enc, color=color_enc, tooltip=tooltip)
            )

        return chart.properties(width="container", height=350).to_dict()
    except Exception as exc:
        logger.error("Chart render failed: %s", exc)
        return {}


def render_chart_from_wide(
    wide_data: dict | None,
    chart_type: str = "bar",
    x_field: str = "dim_0",
    y_field: str = "value",
    color_field: str | None = "geography",
    facet_field: str | None = None,
) -> dict:
    """Render a Vega-Lite spec from the serialised wide-table produced by build_wide_table.

    Returns a Vega-Lite spec dict, or {} on error/no data.
    """
    if not wide_data:
        return {}
    data = wide_data.get("data", [])
    columns = wide_data.get("columns", [])
    if not data or not columns:
        return {}

    try:
        plot_df = wide_to_long(data, columns)
        if plot_df.empty:
            return {}

        def _col(field: str | None, fallback: str) -> str:
            return field if field and field in plot_df.columns else fallback

        x = _col(x_field, plot_df.columns[0])
        y = _col(y_field, "value")
        facet = _col(facet_field, None) if facet_field else None

        def _type(col: str) -> str:
            s = plot_df[col]
            if pd.api.types.is_numeric_dtype(s):
                return "Q"
            if hasattr(s, "cat") and s.cat.ordered:
                return "O"
            return "N"

        def _sort(col: str) -> list | None:
            s = plot_df[col]
            if hasattr(s, "cat") and s.cat.ordered:
                return list(s.cat.categories)
            return None

        def _enc_kwargs(col: str) -> dict:
            sort_order = _sort(col)
            return {"sort": sort_order} if sort_order is not None else {}

        x_enc = alt.X(
            f"{x}:{_type(x)}", title="",
            axis=alt.Axis(labelAngle=-45),
            **_enc_kwargs(x),
        )
        y_enc = alt.Y(f"{y}:{_type(y)}", title=y.replace("_", " ").title(), **_enc_kwargs(y))
        tooltip_fields = list({x, y, color_field, facet} - {None})
        tooltip = [f"{f}:{_type(f)}" for f in tooltip_fields if f in plot_df.columns]

        encode_kwargs: dict = {"x": x_enc, "y": y_enc, "tooltip": tooltip}
        if color_field and color_field in plot_df.columns:
            encode_kwargs["color"] = alt.Color(
                f"{color_field}:{_type(color_field)}", title="", **_enc_kwargs(color_field)
            )
            if chart_type == "bar" and color_field != x:
                encode_kwargs["xOffset"] = alt.XOffset(
                    f"{color_field}:{_type(color_field)}", **_enc_kwargs(color_field)
                )

        mark = {"bar": "bar", "line": "line", "point": "point"}.get(chart_type, "bar")
        mark_kwargs = {"point": True} if mark == "line" else {}

        base = getattr(alt.Chart(plot_df), f"mark_{mark}")(**mark_kwargs).encode(
            **encode_kwargs
        )

        if facet and facet in plot_df.columns:
            facet_enc = alt.Facet(f"{facet}:{_type(facet)}", **_enc_kwargs(facet))
            chart = base.properties(width=200, height=200).facet(
                facet=facet_enc, columns=3,
            )
        else:
            chart = base.properties(width="container", height=350)

        return chart.to_dict()
    except Exception as exc:
        logger.error("Chart render failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Dash registration
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("group-dropdown", "options"),
        Output("group-dropdown", "value"),
        Output("group-dropdown", "disabled"),
        Input("topic-dropdown", "value"),
    )
    def update_group_options(topic_code: str | None):
        return compute_group_options(topic_code)

    @app.callback(
        Output("fetch-button", "disabled"),
        Input("topic-dropdown", "value"),
        Input("group-dropdown", "value"),
        Input("vintage-dropdown", "value"),
        Input("geo-list-store", "data"),
    )
    def toggle_fetch_button(topic, group, vintages, geo_list):
        return compute_fetch_button_disabled(topic, group, vintages, geo_list)

    @app.callback(
        Output("geo-list-store", "data"),
        Input("add-geo-btn", "n_clicks"),
        Input({"type": "remove-geo", "index": ALL}, "n_clicks"),
        State("scope-dropdown", "value"),
        State("sumlevel-dropdown", "value"),
        State("geo-list-store", "data"),
        prevent_initial_call=True,
    )
    def update_geo_list(n_add, n_removes, scope, sumlevel, current_list):
        return compute_geo_list(n_add, n_removes, scope, sumlevel, current_list, dash.ctx.triggered_id)

    @app.callback(
        Output("geo-chips", "children"),
        Input("geo-list-store", "data"),
    )
    def render_geo_chips(geo_list):
        return compute_geo_chips(geo_list)

    @app.callback(
        Output("long-data-store", "data"),
        Output("fetch-status", "children"),
        Output("fetch-error-alert", "children"),
        Output("fetch-error-alert", "is_open"),
        Input("fetch-button", "n_clicks"),
        State("group-dropdown", "value"),
        State("vintage-dropdown", "value"),
        State("geo-list-store", "data"),
        prevent_initial_call=True,
    )
    def fetch_and_store(n_clicks, group_code, vintages, geo_list):
        return compute_fetch_and_store(n_clicks, group_code, vintages, geo_list)

    @app.callback(
        Output("dim-drop-controls", "children"),
        Output("reset-dims-btn", "style"),
        Input("long-data-store", "data"),
        Input("dropped-dims-store", "data"),
    )
    def render_dim_controls(store_data, dropped_dims):
        return compute_dim_controls(store_data, dropped_dims)

    @app.callback(
        Output("dropped-dims-store", "data"),
        Input("long-data-store", "data"),
        Input("reset-dims-btn", "n_clicks"),
        Input({"type": "drop-dim-btn", "index": ALL}, "n_clicks"),
        State("dropped-dims-store", "data"),
        prevent_initial_call=True,
    )
    def update_dropped_dims(store_data, n_reset, n_drops, current_dropped):
        return compute_dropped_dims(n_drops, n_reset, current_dropped, dash.ctx.triggered_id)

    @app.callback(
        Output("wide-data-store", "data"),
        Input("long-data-store", "data"),
        Input("value-mode-radio", "value"),
        Input("show-moe-checkbox", "value"),
        Input("dropped-dims-store", "data"),
    )
    def compute_wide_cb(store_data, value_mode, show_moe, dropped_dims):
        return compute_wide_data(store_data, value_mode, show_moe, dropped_dims)

    @app.callback(
        Output("dim-filter-controls", "children"),
        Input("wide-data-store", "data"),
    )
    def render_dim_filter_controls_cb(wide_data):
        return compute_dim_filter_controls(wide_data)

    @app.callback(
        Output("data-output", "children"),
        Input("wide-data-store", "data"),
        Input({"type": "dim-filter", "index": ALL}, "value"),
        State({"type": "dim-filter", "index": ALL}, "id"),
    )
    def render_table(wide_data, filter_values, filter_ids):
        filters = {
            fid["index"]: fval
            for fid, fval in zip(filter_ids or [], filter_values or [])
            if fval
        }
        data, columns = apply_dim_filters(wide_data, filters)
        if not data:
            return no_update
        table = dash_table.DataTable(
            data=data,
            columns=columns,
            page_size=15,
            sort_action="native",
            filter_action="none",
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "padding": "3px 8px", "fontSize": "12px"},
            style_header={"fontWeight": "bold", "backgroundColor": "#f8f9fa", "fontSize": "12px"},
        )
        return table

    @app.callback(
        Output("chart-x-axis", "options"),
        Output("chart-x-axis", "value"),
        Output("chart-y-axis", "options"),
        Output("chart-y-axis", "value"),
        Output("chart-color-by", "options"),
        Output("chart-color-by", "value"),
        Output("chart-facet", "options"),
        Output("chart-facet", "value"),
        Input("wide-data-store", "data"),
    )
    def update_chart_axis_options(wide_data):
        if not wide_data:
            empty = []
            return empty, None, empty, None, empty, None, empty, None

        options = _chart_axis_options(wide_data)
        vals = [o["value"] for o in options]

        x_default = next((v for v in vals if v.startswith("dim_")), vals[0] if vals else None)
        y_default = "value" if "value" in vals else None
        color_default = "geography" if "geography" in vals else None
        facet_default = None

        return options, x_default, options, y_default, options, color_default, options, facet_default

    @app.callback(
        Output("chart-image", "spec"),
        Input("wide-data-store", "data"),
        Input("chart-type", "value"),
        Input("chart-x-axis", "value"),
        Input("chart-y-axis", "value"),
        Input("chart-color-by", "value"),
        Input("chart-facet", "value"),
    )
    def update_chart(wide_data, chart_type, x_field, y_field, color_field, facet_field):
        return render_chart_from_wide(
            wide_data,
            chart_type or "bar",
            x_field,
            y_field or "value",
            color_field or None,
            facet_field or None,
        )

    @app.callback(
        Output("download-frictionless", "data"),
        Input("export-frictionless-btn", "n_clicks"),
        State("long-data-store", "data"),
        State("group-dropdown", "value"),
        State("vintage-dropdown", "value"),
        State("geo-list-store", "data"),
        prevent_initial_call=True,
    )
    def download_frictionless(n_clicks, store_data, group_code, vintages, geo_list):
        return compute_frictionless_download(store_data, group_code, vintages, geo_list)

    @app.callback(
        Output("download-excel", "data"),
        Input("export-excel-btn", "n_clicks"),
        State("long-data-store", "data"),
        State("group-dropdown", "value"),
        State("vintage-dropdown", "value"),
        State("value-mode-radio", "value"),
        State("show-moe-checkbox", "value"),
        prevent_initial_call=True,
    )
    def download_excel(n_clicks, store_data, group_code, vintages, value_mode, show_moe):
        return compute_excel_download(store_data, group_code, vintages, value_mode, show_moe)
