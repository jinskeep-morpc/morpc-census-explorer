"""Dash callback registration for morpc-census-explorer."""

from __future__ import annotations

import logging

import dash
from dash import Input, Output, State, dash_table, dcc, no_update

logger = logging.getLogger(__name__)

from app.db import SessionLocal
from app.exports import export_excel, export_frictionless
from app.fetch import build_wide_table, deserialise_long, fetch_all_vintages, serialise_long
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
    scope: str | None,
    sumlevel: str | None,
) -> bool:
    """Return True (disabled) unless all five selectors have a value."""
    return not all([topic, group, vintages, scope, sumlevel])


def compute_fetch_and_store(
    n_clicks: int | None,
    group_code: str,
    vintages: list[int],
    scope: str,
    sumlevel: str,
) -> tuple[dict | None, str]:
    """Fetch all vintages and return serialised long DataFrame + status message.

    Returns (store_data, status_text).
    """
    session = None
    try:
        session = SessionLocal()
        long_df = fetch_all_vintages(session, group_code, vintages, scope, sumlevel)
        row_count = len(long_df)
        return serialise_long(long_df), f"Loaded {row_count:,} rows for {group_code}."
    except Exception as exc:
        return no_update, f"Error fetching data: {exc}"
    finally:
        if session is not None:
            session.close()


def compute_table(
    store_data: dict | None,
    value_types: list[str] | None,
) -> tuple[list, list, dict]:
    """Build DataTable data/columns from stored long DataFrame.

    Returns (data, columns, value_type_card_style).
    """
    if not store_data or not value_types:
        return [], [], {"display": "none"}

    long_df = deserialise_long(store_data)
    data, columns = build_wide_table(long_df, value_types)
    return data, columns, {"display": "block"}


def compute_frictionless_download(
    store_data: dict | None,
    group_code: str | None,
    vintages: list[int] | None,
) -> dict | None:
    """Return dcc.send_bytes payload for frictionless zip, or None on error."""
    if not store_data or not group_code or not vintages:
        return no_update
    try:
        long_df = deserialise_long(store_data)
        zip_bytes = export_frictionless(long_df, group_code, vintages)
        vintage_str = "_".join(str(v) for v in sorted(vintages))
        filename = f"census-acs5-{group_code.lower()}-{vintage_str}.zip"
        return dcc.send_bytes(zip_bytes, filename)
    except Exception as exc:
        logger.error("Frictionless export failed: %s", exc)
        return no_update


def compute_excel_download(
    store_data: dict | None,
    group_code: str | None,
    value_types: list[str] | None,
    vintages: list[int] | None,
) -> dict | None:
    """Return dcc.send_bytes payload for Excel .xlsx, or no_update on error."""
    if not store_data or not group_code or not value_types:
        return no_update
    try:
        long_df = deserialise_long(store_data)
        xlsx_bytes = export_excel(long_df, group_code, value_types)
        vintage_str = "_".join(str(v) for v in sorted(vintages or []))
        filename = f"census-acs5-{group_code.lower()}-{vintage_str}.xlsx"
        return dcc.send_bytes(xlsx_bytes, filename)
    except Exception as exc:
        logger.error("Excel export failed: %s", exc)
        return no_update


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
        Input("scope-dropdown", "value"),
        Input("sumlevel-dropdown", "value"),
    )
    def toggle_fetch_button(topic, group, vintages, scope, sumlevel):
        return compute_fetch_button_disabled(topic, group, vintages, scope, sumlevel)

    @app.callback(
        Output("long-data-store", "data"),
        Output("fetch-status", "children"),
        Input("fetch-button", "n_clicks"),
        State("group-dropdown", "value"),
        State("vintage-dropdown", "value"),
        State("scope-dropdown", "value"),
        State("sumlevel-dropdown", "value"),
        prevent_initial_call=True,
    )
    def fetch_and_store(n_clicks, group_code, vintages, scope, sumlevel):
        return compute_fetch_and_store(n_clicks, group_code, vintages, scope, sumlevel)

    @app.callback(
        Output("data-output", "children"),
        Output("value-type-card", "style"),
        Input("long-data-store", "data"),
        Input("value-type-checklist", "value"),
    )
    def render_table(store_data, value_types):
        data, columns, card_style = compute_table(store_data, value_types)
        if not data:
            return no_update, card_style
        table = dash_table.DataTable(
            data=data,
            columns=columns,
            page_size=25,
            sort_action="native",
            filter_action="native",
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "padding": "6px 12px", "fontSize": "13px"},
            style_header={"fontWeight": "bold", "backgroundColor": "#f8f9fa"},
        )
        return table, card_style

    @app.callback(
        Output("download-frictionless", "data"),
        Input("export-frictionless-btn", "n_clicks"),
        State("long-data-store", "data"),
        State("group-dropdown", "value"),
        State("vintage-dropdown", "value"),
        prevent_initial_call=True,
    )
    def download_frictionless(n_clicks, store_data, group_code, vintages):
        return compute_frictionless_download(store_data, group_code, vintages)

    @app.callback(
        Output("download-excel", "data"),
        Input("export-excel-btn", "n_clicks"),
        State("long-data-store", "data"),
        State("group-dropdown", "value"),
        State("vintage-dropdown", "value"),
        State("value-type-checklist", "value"),
        prevent_initial_call=True,
    )
    def download_excel(n_clicks, store_data, group_code, vintages, value_types):
        return compute_excel_download(store_data, group_code, value_types, vintages)
