"""Top-level Dash layout for morpc-census-explorer."""

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.selectors import scope_options, sumlevel_options, topic_options, vintage_options

_VALUE_TYPE_OPTIONS = [
    {"label": "Estimate", "value": "estimate"},
    {"label": "MOE", "value": "moe"},
    {"label": "Percent Estimate", "value": "percent_estimate"},
    {"label": "Percent MOE", "value": "percent_moe"},
]


def make_layout() -> dbc.Container:
    return dbc.Container(
        [
            # Client-side store for the long DataFrame (survives filter changes without re-fetch)
            dcc.Store(id="long-data-store"),
            # Download triggers
            dcc.Download(id="download-frictionless"),
            dcc.Download(id="download-excel"),

            # Header
            dbc.Row(
                dbc.Col(
                    html.Div(
                        html.H2("MORPC Census Explorer"),
                        className="morpc-header",
                    )
                )
            ),

            # Error alert (hidden until a fetch error occurs)
            dbc.Row(
                dbc.Col(
                    dbc.Alert(
                        id="fetch-error-alert",
                        color="danger",
                        is_open=False,
                        dismissable=True,
                    )
                )
            ),

            # Selector card
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                # Row 1: topic + group
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Label("Topic"),
                                                dcc.Dropdown(
                                                    id="topic-dropdown",
                                                    options=topic_options(),
                                                    placeholder="Select a topic…",
                                                    clearable=True,
                                                ),
                                            ],
                                            md=6,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Group"),
                                                dcc.Dropdown(
                                                    id="group-dropdown",
                                                    options=[],
                                                    placeholder="Select a topic first…",
                                                    clearable=True,
                                                    disabled=True,
                                                ),
                                            ],
                                            md=6,
                                        ),
                                    ],
                                    className="mb-3",
                                ),

                                # Row 2: vintage + scope + sumlevel
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Label("Vintage(s)"),
                                                dcc.Dropdown(
                                                    id="vintage-dropdown",
                                                    options=vintage_options(),
                                                    placeholder="Select one or more…",
                                                    multi=True,
                                                ),
                                            ],
                                            md=4,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Scope"),
                                                dcc.Dropdown(
                                                    id="scope-dropdown",
                                                    options=scope_options(),
                                                    placeholder="Select a scope…",
                                                    clearable=True,
                                                ),
                                            ],
                                            md=4,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Summary Level"),
                                                dcc.Dropdown(
                                                    id="sumlevel-dropdown",
                                                    options=sumlevel_options(),
                                                    placeholder="Select a level…",
                                                    clearable=True,
                                                ),
                                            ],
                                            md=4,
                                        ),
                                    ],
                                    className="mb-3",
                                ),

                                # Row 3: fetch button + status
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dbc.Button(
                                                "Fetch Data",
                                                id="fetch-button",
                                                color="primary",
                                                disabled=True,
                                            ),
                                            width="auto",
                                        ),
                                        dbc.Col(
                                            html.Small(
                                                id="fetch-status",
                                                className="text-muted align-self-center",
                                            )
                                        ),
                                    ],
                                    align="center",
                                ),
                            ]
                        )
                    )
                )
            ),

            # Value-type filter + export buttons (shown only when data is loaded)
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.Label("Show value type(s):", className="fw-bold"),
                                                dbc.Checklist(
                                                    id="value-type-checklist",
                                                    options=_VALUE_TYPE_OPTIONS,
                                                    value=["estimate"],
                                                    inline=True,
                                                ),
                                            ],
                                            md=8,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label("Export:", className="fw-bold"),
                                                dbc.ButtonGroup(
                                                    [
                                                        dbc.Button(
                                                            "Frictionless (zip)",
                                                            id="export-frictionless-btn",
                                                            color="secondary",
                                                            outline=True,
                                                            size="sm",
                                                        ),
                                                        dbc.Button(
                                                            "Excel (.xlsx)",
                                                            id="export-excel-btn",
                                                            color="secondary",
                                                            outline=True,
                                                            size="sm",
                                                        ),
                                                    ]
                                                ),
                                            ],
                                            md=4,
                                            className="d-flex flex-column align-items-end",
                                        ),
                                    ],
                                    align="center",
                                ),
                            ]
                        ),
                        className="mt-3",
                    ),
                    id="value-type-card",
                    style={"display": "none"},
                )
            ),

            # Data table output (wrapped in Loading spinner)
            dbc.Row(
                dbc.Col(
                    dcc.Loading(
                        id="loading-output",
                        type="default",
                        color="var(--morpc-green)",
                        children=html.Div(id="data-output"),
                    ),
                    className="mt-3",
                )
            ),
        ],
        fluid=True,
    )
