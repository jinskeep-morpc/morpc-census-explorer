"""Dash callback registration for morpc-census-explorer."""

from __future__ import annotations

import dash
from dash import Input, Output

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
