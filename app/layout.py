"""Top-level Dash layout for morpc-census-explorer."""

import dash_bootstrap_components as dbc
import dash_vega_components as dvc
from dash import dcc, html

from app.selectors import scope_options, sumlevel_options, topic_options, vintage_options


def make_layout() -> dbc.Container:
    return dbc.Container(
        [
            # Client-side stores
            dcc.Store(id="long-data-store"),
            dcc.Store(id="geo-list-store", data=[]),
            dcc.Store(id="dropped-dims-store", data=[]),
            dcc.Store(id="wide-data-store"),
            # Download triggers
            dcc.Download(id="download-frictionless"),
            dcc.Download(id="download-excel"),

            # Header
            dbc.Row(
                dbc.Col(
                    html.Div(
                        html.H4("MORPC Census Explorer", className="mb-0"),
                        className="morpc-header",
                    )
                )
            ),

            # Body: sidebar + main content
            dbc.Row(
                [
                    # ── Sidebar ──────────────────────────────────────────────
                    dbc.Col(
                        html.Div(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        # Error alert (lives in sidebar, near fetch button)
                                        dbc.Alert(
                                            id="fetch-error-alert",
                                            color="danger",
                                            is_open=False,
                                            dismissable=True,
                                            className="p-2 mb-2 small",
                                        ),

                                        # Data selection
                                        dbc.Label("Topic", className="fw-semibold mb-1 small"),
                                        dcc.Dropdown(
                                            id="topic-dropdown",
                                            options=topic_options(),
                                            placeholder="Select a topic…",
                                            clearable=True,
                                            className="mb-2",
                                        ),

                                        dbc.Label("Group", className="fw-semibold mb-1 small"),
                                        dcc.Dropdown(
                                            id="group-dropdown",
                                            options=[],
                                            placeholder="Select a topic first…",
                                            clearable=True,
                                            disabled=True,
                                            className="mb-2",
                                        ),

                                        dbc.Label("Vintage(s)", className="fw-semibold mb-1 small"),
                                        dcc.Dropdown(
                                            id="vintage-dropdown",
                                            options=vintage_options(),
                                            placeholder="One or more…",
                                            multi=True,
                                            className="mb-2",
                                        ),

                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Scope", className="fw-semibold mb-1 small"),
                                                        dcc.Dropdown(
                                                            id="scope-dropdown",
                                                            options=scope_options(),
                                                            placeholder="Scope…",
                                                            clearable=True,
                                                        ),
                                                    ]
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Sumlevel", className="fw-semibold mb-1 small"),
                                                        dcc.Dropdown(
                                                            id="sumlevel-dropdown",
                                                            options=sumlevel_options(),
                                                            placeholder="Level…",
                                                            clearable=True,
                                                        ),
                                                    ]
                                                ),
                                            ],
                                            className="mb-2",
                                        ),

                                        dbc.Button(
                                            "+ Add Geography",
                                            id="add-geo-btn",
                                            color="secondary",
                                            outline=True,
                                            size="sm",
                                            className="w-100 mb-2",
                                        ),
                                        html.Div(id="geo-chips", className="mb-2"),

                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    dbc.Button(
                                                        "Fetch Data",
                                                        id="fetch-button",
                                                        color="primary",
                                                        size="sm",
                                                        disabled=True,
                                                        className="w-100",
                                                    ),
                                                    width=7,
                                                ),
                                                dbc.Col(
                                                    dcc.Loading(
                                                        html.Small(
                                                            id="fetch-status",
                                                            className="text-muted d-block",
                                                        ),
                                                        type="circle",
                                                        color="var(--morpc-green)",
                                                        style={"display": "inline-block"},
                                                    ),
                                                    width=5,
                                                ),
                                            ],
                                            align="center",
                                        ),

                                        html.Hr(className="my-2"),

                                        # Display options
                                        dbc.Label("Table view", className="fw-semibold mb-1 small"),
                                        dbc.RadioItems(
                                            id="value-mode-radio",
                                            options=[
                                                {"label": "Estimate", "value": "estimate"},
                                                {"label": "Percent", "value": "percent"},
                                            ],
                                            value="estimate",
                                            inline=True,
                                            className="mb-1 small",
                                        ),
                                        dbc.Checkbox(
                                            id="show-moe-checkbox",
                                            label="Display MOE",
                                            value=False,
                                            className="mb-2 small",
                                        ),

                                        html.Hr(className="my-2"),

                                        # Chart options
                                        dbc.Label("Chart", className="fw-semibold mb-1 small"),
                                        dbc.Label("Chart type", className="small mb-0"),
                                        dcc.Dropdown(
                                            id="chart-type",
                                            options=[
                                                {"label": "Bar", "value": "bar"},
                                                {"label": "Line", "value": "line"},
                                                {"label": "Point", "value": "point"},
                                            ],
                                            value="bar",
                                            clearable=False,
                                            className="mb-1",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        dbc.Label("X axis", className="small mb-0"),
                                                        dcc.Dropdown(
                                                            id="chart-x-axis",
                                                            options=[],
                                                            value=None,
                                                            clearable=False,
                                                        ),
                                                    ]
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Y axis", className="small mb-0"),
                                                        dcc.Dropdown(
                                                            id="chart-y-axis",
                                                            options=[],
                                                            value=None,
                                                            clearable=False,
                                                        ),
                                                    ]
                                                ),
                                            ],
                                            className="mb-1 g-1",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Color by", className="small mb-0"),
                                                        dcc.Dropdown(
                                                            id="chart-color-by",
                                                            options=[],
                                                            value=None,
                                                            clearable=True,
                                                        ),
                                                    ]
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Facet by", className="small mb-0"),
                                                        dcc.Dropdown(
                                                            id="chart-facet",
                                                            options=[],
                                                            value=None,
                                                            clearable=True,
                                                            placeholder="None",
                                                        ),
                                                    ]
                                                ),
                                            ],
                                            className="mb-1 g-1",
                                        ),

                                        html.Hr(className="my-2"),

                                        # Export
                                        dbc.Label("Export", className="fw-semibold mb-1 small"),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        dbc.Button(
                                                            "Frictionless",
                                                            id="export-frictionless-btn",
                                                            color="secondary",
                                                            outline=True,
                                                            size="sm",
                                                            className="w-100 mb-1",
                                                        ),
                                                        html.Small(
                                                            "CSV + metadata descriptor (datapackage.json)",
                                                            className="text-muted",
                                                        ),
                                                    ]
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Button(
                                                            "Excel (.xlsx)",
                                                            id="export-excel-btn",
                                                            color="secondary",
                                                            outline=True,
                                                            size="sm",
                                                            className="w-100 mb-1",
                                                        ),
                                                        html.Small(
                                                            "Workbook with data table and chart",
                                                            className="text-muted",
                                                        ),
                                                    ]
                                                ),
                                            ],
                                            className="mb-2 g-2",
                                        ),
                                    ],
                                    className="p-2",
                                ),
                            ),
                            style={
                                "position": "sticky",
                                "top": "1rem",
                            },
                        ),
                        md=3,
                    ),

                    # ── Main content ──────────────────────────────────────────
                    dbc.Col(
                        [
                            # Dim drop controls
                            html.Div(
                                [
                                    html.Div(
                                        id="dim-drop-controls",
                                        className="d-inline-flex flex-wrap align-items-center gap-2",
                                    ),
                                    dbc.Button(
                                        "Reset Dimensions",
                                        id="reset-dims-btn",
                                        size="sm",
                                        color="secondary",
                                        outline=True,
                                        n_clicks=0,
                                        style={"display": "none"},
                                        className="ms-2",
                                    ),
                                ],
                                className="mb-2",
                            ),

                            # Dim column filter dropdowns
                            html.Div(
                                id="dim-filter-controls",
                                className="d-flex flex-wrap gap-2 align-items-center mb-2",
                            ),

                            # Table
                            dcc.Loading(
                                id="loading-output",
                                type="default",
                                color="var(--morpc-green)",
                                children=html.Div(id="data-output"),
                            ),

                            # Chart (below table, reactive to table state)
                            dcc.Loading(
                                dvc.Vega(
                                    id="chart-image",
                                    spec={},
                                    opt={"actions": False},
                                    style={"width": "100%", "marginTop": "1rem"},
                                ),
                                type="default",
                                color="var(--morpc-green)",
                            ),
                        ],
                        md=9,
                    ),
                ],
                className="mt-2",
            ),
        ],
        fluid=True,
    )
