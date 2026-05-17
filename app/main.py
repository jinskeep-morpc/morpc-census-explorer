import os

import dash
import dash_bootstrap_components as dbc
from dotenv import load_dotenv

from app.callbacks import register_callbacks
from app.layout import make_layout

load_dotenv()

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="MORPC Census Explorer",
)

app.layout = make_layout()
register_callbacks(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
