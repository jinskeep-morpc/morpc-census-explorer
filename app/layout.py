"""Top-level Dash layout for morpc-census-explorer."""

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.selectors import scope_options, sumlevel_options, topic_options, vintage_options


def make_layout() -> dbc.Container:
    return dbc.Container(
        [
            # Header
            dbc.Row(
                dbc.Col(html.H2("MORPC Census Explorer", className="my-3"))
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
                                # Row 3: fetch button
                                dbc.Row(
                                    dbc.Col(
                                        dbc.Button(
                                            "Fetch Data",
                                            id="fetch-button",
                                            color="primary",
                                            disabled=True,
                                        )
                                    )
                                ),
                            ]
                        )
                    )
                )
            ),
            # Output area (populated in Phase 4)
            dbc.Row(
                dbc.Col(html.Div(id="data-output"), className="mt-3")
            ),
        ],
        fluid=True,
    )
