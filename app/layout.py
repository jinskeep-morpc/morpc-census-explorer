"""Top-level Dash layout for morpc-census-explorer."""

import dash_bootstrap_components as dbc
import dash_vega_components as dvc
from dash import dcc, html

from app.selectors import scope_options, sumlevel_options, survey_options, topic_options, vintage_options


def _tip(label_text, tip_id, tooltip_text, label_cls="fw-semibold mb-1 small"):
    """Return [Label-with-info-icon, Tooltip] for use in accordion item children."""
    return [
        dbc.Label(
            [
                label_text,
                " ",
                html.Sup(
                    "ⓘ",
                    id=tip_id,
                    style={"cursor": "help", "color": "#6c757d", "fontSize": "0.7em"},
                ),
            ],
            className=label_cls,
        ),
        dbc.Tooltip(tooltip_text, target=tip_id, placement="right"),
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
                            [
                                # Error alert — always visible above the accordion
                                dbc.Alert(
                                    id="fetch-error-alert",
                                    color="danger",
                                    is_open=False,
                                    dismissable=True,
                                    className="p-2 mb-2 small",
                                ),

                                dbc.Accordion(
                                    [
                                        # ── Step 1: Select Data ──────────────
                                        dbc.AccordionItem(
                                            [
                                                *_tip(
                                                    "Survey", "tip-survey",
                                                    "The Census survey or dataset to query. "
                                                    "ACS surveys provide annual estimates with margins of error. "
                                                    "Decennial surveys are conducted every 10 years (2010, 2020) without margins of error.",
                                                ),
                                                dcc.Dropdown(
                                                    id="survey-dropdown",
                                                    options=survey_options(),
                                                    value="acs/acs5",
                                                    clearable=False,
                                                    className="mb-2",
                                                ),

                                                *_tip(
                                                    "Topic", "tip-topic",
                                                    "A broad Census subject area (e.g., Demographics, Housing, Economics) "
                                                    "that groups related data tables.",
                                                ),
                                                dcc.Dropdown(
                                                    id="topic-dropdown",
                                                    options=topic_options(),
                                                    placeholder="Select a topic…",
                                                    clearable=True,
                                                    className="mb-2",
                                                ),

                                                *_tip(
                                                    "Group", "tip-group",
                                                    "A specific Census data table within the topic (e.g., B01001 — Sex by Age). "
                                                    "Each group contains a set of related variables.",
                                                ),
                                                dcc.Dropdown(
                                                    id="group-dropdown",
                                                    options=[],
                                                    placeholder="Select a group…",
                                                    clearable=True,
                                                    disabled=True,
                                                    className="mb-2",
                                                ),

                                                *_tip(
                                                    "Vintage(s)", "tip-vintage",
                                                    "The survey year(s) to retrieve. Select multiple years to compare across time. "
                                                    "Available years depend on the selected survey.",
                                                ),
                                                dcc.Dropdown(
                                                    id="vintage-dropdown",
                                                    options=vintage_options("acs/acs5"),
                                                    placeholder="One or more…",
                                                    multi=True,
                                                ),
                                            ],
                                            title="1. Select Data",
                                            item_id="step-data",
                                        ),

                                        # ── Step 2: Select Geography ──────────
                                        dbc.AccordionItem(
                                            [
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                *_tip(
                                                                    "Scope", "tip-scope",
                                                                    "The geographic area to query (e.g., a county, "
                                                                    "a multi-county region, or a state).",
                                                                ),
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
                                                                *_tip(
                                                                    "Sumlevel", "tip-sumlevel",
                                                                    "The level of geographic detail to return within the scope "
                                                                    "(e.g., county-level or tract-level summaries).",
                                                                ),
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
                                            ],
                                            title="2. Select Geography",
                                            item_id="step-geo",
                                        ),

                                        # ── Step 3: Select Data Type ──────────
                                        dbc.AccordionItem(
                                            [
                                                *_tip(
                                                    "Values", "tip-values",
                                                    "Estimate shows raw Census counts. Percent expresses each row "
                                                    "as a share of the universe total.",
                                                ),
                                                dbc.RadioItems(
                                                    id="value-mode-radio",
                                                    options=[
                                                        {"label": "Estimate", "value": "estimate"},
                                                        {"label": "Percent", "value": "percent"},
                                                    ],
                                                    value="estimate",
                                                    inline=True,
                                                    className="mb-2 small",
                                                ),
                                                *_tip(
                                                    "Margin of Error", "tip-moe",
                                                    "Show the Margin of Error alongside each estimate. "
                                                    "MOE indicates the range of statistical uncertainty at the 90% confidence level.",
                                                    label_cls="mb-1 small",
                                                ),
                                                dbc.Checkbox(
                                                    id="show-moe-checkbox",
                                                    label="Display MOE",
                                                    value=False,
                                                    className="small",
                                                ),
                                            ],
                                            title="3. Select Data Type",
                                            item_id="step-table",
                                        ),

                                        # ── Step 4: Configure Chart ───────────
                                        dbc.AccordionItem(
                                            [
                                                *_tip(
                                                    "Chart type", "tip-chart-type",
                                                    "The visual form of the chart. Bar charts compare categories; "
                                                    "line and area charts show trends over time; stacked and percent "
                                                    "variants show composition.",
                                                ),
                                                dcc.Dropdown(
                                                    id="chart-type",
                                                    options=[
                                                        {"label": "Bar", "value": "bar"},
                                                        {"label": "Stacked Bar", "value": "bar_stacked"},
                                                        {"label": "Horizontal Bar", "value": "bar_horizontal"},
                                                        {"label": "Line", "value": "line"},
                                                        {"label": "Point", "value": "point"},
                                                        {"label": "Percent Bar", "value": "bar_percent"},
                                                        {"label": "Stacked Area", "value": "area_stacked"},
                                                        {"label": "Percent Area", "value": "area_percent"},
                                                    ],
                                                    value="bar",
                                                    clearable=False,
                                                    className="mb-2",
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                *_tip(
                                                                    "X axis", "tip-x-axis",
                                                                    "The variable displayed along the horizontal axis.",
                                                                    label_cls="small mb-0",
                                                                ),
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
                                                                *_tip(
                                                                    "Y axis", "tip-y-axis",
                                                                    "The variable plotted on the vertical axis — "
                                                                    "typically the estimate or calculated value.",
                                                                    label_cls="small mb-0",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id="chart-y-axis",
                                                                    options=[],
                                                                    value=None,
                                                                    clearable=False,
                                                                ),
                                                            ]
                                                        ),
                                                    ],
                                                    className="mb-2 g-1",
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                *_tip(
                                                                    "Color by", "tip-color-by",
                                                                    "Split the chart by this variable, assigning a "
                                                                    "distinct color to each of its values.",
                                                                    label_cls="small mb-0",
                                                                ),
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
                                                                *_tip(
                                                                    "Facet by", "tip-facet-by",
                                                                    "Create a separate sub-panel for each value of "
                                                                    "this variable.",
                                                                    label_cls="small mb-0",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id="chart-facet",
                                                                    options=[],
                                                                    value=None,
                                                                    clearable=True,
                                                                    placeholder="None",
                                                                    className="mb-1",
                                                                ),
                                                                dbc.Checkbox(
                                                                    id="chart-facet-independent-y",
                                                                    label="Independent y-axis",
                                                                    value=False,
                                                                    className="small",
                                                                ),
                                                                dbc.Checkbox(
                                                                    id="chart-facet-independent-x",
                                                                    label="Independent x-axis",
                                                                    value=False,
                                                                    className="small",
                                                                ),
                                                            ]
                                                        ),
                                                    ],
                                                    className="mb-2 g-1",
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                *_tip(
                                                                    "Width (in)", "tip-width",
                                                                    "Chart width in inches, rendered at 96 px per inch.",
                                                                    label_cls="small mb-0",
                                                                ),
                                                                dbc.Input(
                                                                    id="chart-width",
                                                                    type="number",
                                                                    value=8,
                                                                    min=2,
                                                                    max=24,
                                                                    step=0.5,
                                                                    className="mb-1",
                                                                ),
                                                            ]
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                *_tip(
                                                                    "Height (in)", "tip-height",
                                                                    "Chart height in inches, rendered at 96 px per inch.",
                                                                    label_cls="small mb-0",
                                                                ),
                                                                dbc.Input(
                                                                    id="chart-height",
                                                                    type="number",
                                                                    value=5,
                                                                    min=2,
                                                                    max=16,
                                                                    step=0.5,
                                                                    className="mb-1",
                                                                ),
                                                            ]
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                *_tip(
                                                                    "Font size", "tip-font-size",
                                                                    "Base font size in points for all chart text. "
                                                                    "Titles scale at 1.3×, axis labels at 1.0×, captions at 0.8×.",
                                                                    label_cls="small mb-0",
                                                                ),
                                                                dbc.Input(
                                                                    id="chart-font-size",
                                                                    type="number",
                                                                    value=12,
                                                                    min=8,
                                                                    max=24,
                                                                    step=1,
                                                                    className="mb-1",
                                                                ),
                                                            ]
                                                        ),
                                                    ],
                                                    className="g-1",
                                                ),
                                            ],
                                            title="4. Configure Chart",
                                            item_id="step-chart",
                                        ),

                                        # ── Step 5: Export ────────────────────
                                        dbc.AccordionItem(
                                            [
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
                                                                    "CSV + metadata descriptor",
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
                                                                    "Workbook with table and chart",
                                                                    className="text-muted",
                                                                ),
                                                            ]
                                                        ),
                                                    ],
                                                    className="g-2",
                                                ),
                                            ],
                                            title="5. Export",
                                            item_id="step-export",
                                        ),
                                    ],
                                    id="sidebar-accordion",
                                    active_item=["step-data", "step-geo"],
                                    always_open=True,
                                    flush=True,
                                    className="border rounded",
                                ),
                            ],
                            style={
                                "position": "sticky",
                                "top": "1rem",
                                "zIndex": 200,
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
