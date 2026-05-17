import os

import dash
import dash_bootstrap_components as dbc
from dash import html
from dotenv import load_dotenv

load_dotenv()

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="MORPC Census Explorer",
)

app.layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.H1("MORPC Census Explorer", className="my-4"),
            )
        ),
        dbc.Row(
            dbc.Col(
                dbc.Alert(
                    "Application coming soon. Data selection UI is under construction.",
                    color="info",
                )
            )
        ),
    ],
    fluid=True,
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
