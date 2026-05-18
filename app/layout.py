"""Top-level Dash layout for morpc-census-explorer."""

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.selectors import scope_options, sumlevel_options, topic_options, vintage_options


_CHART_X_OPTIONS = [
    {"label": "Variable label", "value": "variable_label"},
    {"label": "Vintage (year)", "value": "reference_period"},
    {"label": "Geography name", "value": "name"},
]

_CHART_Y_OPTIONS = [
    {"label": "Estimate", "value": "estimate"},
    {"label": "MOE", "value": "moe"},
]

_CHART_COLOR_OPTIONS = [
    {"label": "Vintage (year)", "value": "reference_period"},
    {"label": "Geography name", "value": "name"},
    {"label": "Variable label", "value": "variable_label"},
]

_CHART_TYPE_OPTIONS = [
    {"label": "Bar", "value": "bar"},
    {"label": "Line", "value": "line"},
    {"label": "Point", "value": "point"},
]


def make_layout() -> dbc.Container:
    return dbc.Container(
        [
            # Client-side stores
            dcc.Store(id="long-data-store"),
            dcc.Store(id="geo-list-store", data=[]),
            dcc.Store(id="dropped-dims-store", data=[]),
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

                                # Row 2: vintage + scope + sumlevel + Add Geography button
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
                                            md=3,
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
                                            md=3,
                                        ),
                                        dbc.Col(
                                            [
                                                dbc.Label(" "),  # non-breaking space aligns button
                                                dbc.Button(
                                                    "Add Geography",
                                                    id="add-geo-btn",
                                                    color="secondary",
                                                    outline=True,
                                                    size="sm",
                                                    className="w-100",
                                                ),
                                            ],
                                            md=2,
                                        ),
                                    ],
                                    className="mb-2",
                                ),

                                # Row 2.5: selected geographies display
                                dbc.Row(
                                    dbc.Col(
                                        html.Div(
                                            id="geo-chips",
                                            className="mb-2",
                                        )
                                    )
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
                                                dbc.Label("View:", className="fw-bold me-2"),
                                                dbc.RadioItems(
                                                    id="value-mode-radio",
                                                    options=[
                                                        {"label": "Estimate", "value": "estimate"},
                                                        {"label": "Percent", "value": "percent"},
                                                    ],
                                                    value="estimate",
                                                    inline=True,
                                                    className="d-inline-flex me-4",
                                                ),
                                                dbc.Checkbox(
                                                    id="show-moe-checkbox",
                                                    label="Display MOE",
                                                    value=False,
                                                    className="d-inline-block",
                                                ),
                                            ],
                                            md=8,
                                            className="d-flex align-items-center",
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

            # Tabbed output: Table | Chart
            dbc.Row(
                dbc.Col(
                    dbc.Tabs(
                        [
                            dbc.Tab(
                                [
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
                                            ),
                                        ],
                                        className="mt-2 mb-2",
                                    ),
                                    dcc.Loading(
                                        id="loading-output",
                                        type="default",
                                        color="var(--morpc-green)",
                                        children=html.Div(id="data-output"),
                                    ),
                                ],
                                label="Table",
                                tab_id="tab-table",
                            ),
                            dbc.Tab(
                                [
                                    # Chart controls
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    dbc.Label("X axis"),
                                                    dcc.Dropdown(
                                                        id="chart-x-axis",
                                                        options=_CHART_X_OPTIONS,
                                                        value="variable_label",
                                                        clearable=False,
                                                    ),
                                                ],
                                                md=3,
                                            ),
                                            dbc.Col(
                                                [
                                                    dbc.Label("Y axis"),
                                                    dcc.Dropdown(
                                                        id="chart-y-axis",
                                                        options=_CHART_Y_OPTIONS,
                                                        value="estimate",
                                                        clearable=False,
                                                    ),
                                                ],
                                                md=3,
                                            ),
                                            dbc.Col(
                                                [
                                                    dbc.Label("Color by"),
                                                    dcc.Dropdown(
                                                        id="chart-color-by",
                                                        options=_CHART_COLOR_OPTIONS,
                                                        value="reference_period",
                                                        clearable=False,
                                                    ),
                                                ],
                                                md=3,
                                            ),
                                            dbc.Col(
                                                [
                                                    dbc.Label("Chart type"),
                                                    dcc.Dropdown(
                                                        id="chart-type",
                                                        options=_CHART_TYPE_OPTIONS,
                                                        value="bar",
                                                        clearable=False,
                                                    ),
                                                ],
                                                md=3,
                                            ),
                                        ],
                                        className="mt-3 mb-3",
                                    ),
                                    dcc.Loading(
                                        html.Img(
                                            id="chart-image",
                                            style={"maxWidth": "100%"},
                                        ),
                                        type="default",
                                        color="var(--morpc-green)",
                                    ),
                                ],
                                label="Chart",
                                tab_id="tab-chart",
                            ),
                        ],
                        id="output-tabs",
                        active_tab="tab-table",
                    ),
                    className="mt-3",
                )
            ),
        ],
        fluid=True,
    )
