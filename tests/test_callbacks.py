"""Unit tests for callback logic in app/callbacks.py."""

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from app.callbacks import (
    _friendly_error,
    compute_dim_controls,
    compute_dropped_dims,
    compute_fetch_and_store,
    compute_fetch_button_disabled,
    compute_geo_chips,
    compute_geo_list,
    compute_group_options,
    render_chart_from_wide,
    render_chart_image,
)
from app.fetch import build_wide_table, serialise_long

_GEO = [{"scope": "franklin", "sumlevel": "140"}]


class TestComputeGroupOptions:
    def test_no_topic_returns_disabled(self):
        options, value, disabled = compute_group_options(None)
        assert options == []
        assert value is None
        assert disabled is True

    def test_topic_enables_dropdown(self):
        grps = [{"label": "B01001 — Sex by Age", "value": "B01001"}]
        with patch("app.callbacks.group_options_for_topic", return_value=grps):
            options, value, disabled = compute_group_options("01")
        assert disabled is False
        assert options == grps

    def test_topic_resets_value_to_none(self):
        with patch("app.callbacks.group_options_for_topic", return_value=[{"label": "X", "value": "X"}]):
            _, value, _ = compute_group_options("01")
        assert value is None

    def test_empty_topic_string_disables(self):
        options, value, disabled = compute_group_options("")
        assert disabled is True


class TestComputeFetchButtonDisabled:
    def test_disabled_when_all_none(self):
        assert compute_fetch_button_disabled(None, None, None, None) is True

    def test_enabled_when_all_provided(self):
        assert compute_fetch_button_disabled("01", "B01001", [2023], _GEO) is False

    def test_disabled_when_vintages_empty_list(self):
        assert compute_fetch_button_disabled("01", "B01001", [], _GEO) is True

    def test_disabled_when_geo_list_empty(self):
        assert compute_fetch_button_disabled("01", "B01001", [2023], []) is True

    def test_disabled_when_geo_list_none(self):
        assert compute_fetch_button_disabled("01", "B01001", [2023], None) is True

    def test_disabled_when_group_missing(self):
        assert compute_fetch_button_disabled("01", None, [2023], _GEO) is True

    def test_disabled_when_topic_missing(self):
        assert compute_fetch_button_disabled(None, "B01001", [2023], _GEO) is True

    def test_multiple_vintages_still_enabled(self):
        assert compute_fetch_button_disabled("01", "B01001", [2023, 2022], _GEO) is False

    def test_multiple_geos_still_enabled(self):
        two_geos = [{"scope": "franklin", "sumlevel": "140"}, {"scope": "licking", "sumlevel": "050"}]
        assert compute_fetch_button_disabled("01", "B01001", [2023], two_geos) is False


# ---------------------------------------------------------------------------
# compute_geo_list
# ---------------------------------------------------------------------------

class TestComputeGeoList:
    def test_add_new_geography(self):
        result = compute_geo_list(1, [], "franklin", "050", [], "add-geo-btn")
        assert result == [{"scope": "franklin", "sumlevel": "050"}]

    def test_add_is_deduplicated(self):
        existing = [{"scope": "franklin", "sumlevel": "050"}]
        result = compute_geo_list(1, [], "franklin", "050", existing, "add-geo-btn")
        assert result == existing

    def test_add_second_geography(self):
        existing = [{"scope": "franklin", "sumlevel": "050"}]
        result = compute_geo_list(1, [], "licking", "050", existing, "add-geo-btn")
        assert len(result) == 2

    def test_add_does_nothing_when_scope_missing(self):
        result = compute_geo_list(1, [], None, "050", [], "add-geo-btn")
        assert result == []

    def test_remove_by_index(self):
        geos = [
            {"scope": "franklin", "sumlevel": "050"},
            {"scope": "licking", "sumlevel": "050"},
        ]
        result = compute_geo_list(None, [1, 0], None, None, geos, {"type": "remove-geo", "index": 0})
        assert result == [{"scope": "licking", "sumlevel": "050"}]

    def test_remove_last_geography(self):
        geos = [{"scope": "franklin", "sumlevel": "050"}]
        result = compute_geo_list(None, [1], None, None, geos, {"type": "remove-geo", "index": 0})
        assert result == []


# ---------------------------------------------------------------------------
# compute_geo_chips
# ---------------------------------------------------------------------------

class TestComputeGeoChips:
    def test_empty_list_returns_placeholder(self):
        result = compute_geo_chips([])
        assert len(result) == 1

    def test_none_list_returns_placeholder(self):
        result = compute_geo_chips(None)
        assert len(result) == 1

    def test_one_geo_returns_one_chip(self):
        result = compute_geo_chips([{"scope": "franklin", "sumlevel": "050"}])
        assert len(result) == 1

    def test_two_geos_return_two_chips(self):
        geos = [{"scope": "franklin", "sumlevel": "050"}, {"scope": "licking", "sumlevel": "140"}]
        result = compute_geo_chips(geos)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _friendly_error
# ---------------------------------------------------------------------------

class TestFriendlyError:
    def test_operational_error_message(self):
        class OperationalError(Exception): pass
        result = _friendly_error(OperationalError("could not connect"))
        assert "database" in result.lower() or "connection" in result.lower()

    def test_timeout_message(self):
        class TimeoutError(Exception): pass
        result = _friendly_error(TimeoutError("request timed out"))
        assert "timeout" in result.lower() or "timed out" in result.lower()

    def test_generic_exception_includes_type_name(self):
        class WeirdError(Exception): pass
        result = _friendly_error(WeirdError("something broke"))
        assert "WeirdError" in result


# ---------------------------------------------------------------------------
# compute_fetch_and_store (4-tuple return, now uses fetch_all_geos)
# ---------------------------------------------------------------------------

def _make_long():
    return pd.DataFrame([{
        "geoidfq": "050US39049",
        "name": "Franklin County",
        "reference_period": 2023,
        "survey": "acs/acs5",
        "concept": "Sex by Age",
        "universe": "Total population",
        "variable_label": "Total",
        "variable": "B01001_001",
        "estimate": 1_300_000.0,
        "moe": 50_000.0,
    }])


class TestComputeFetchAndStore:
    def _mock_session(self):
        return MagicMock()

    def test_returns_four_tuple(self):
        with patch("app.callbacks.SessionLocal", return_value=self._mock_session()), \
             patch("app.callbacks.fetch_all_geos", return_value=_make_long()):
            result = compute_fetch_and_store(1, "B01001", [2023], _GEO)
        assert len(result) == 4

    def test_success_returns_store_and_status(self):
        with patch("app.callbacks.SessionLocal", return_value=self._mock_session()), \
             patch("app.callbacks.fetch_all_geos", return_value=_make_long()):
            store, status, err_msg, err_open = compute_fetch_and_store(1, "B01001", [2023], _GEO)
        assert store is not None
        assert "B01001" in status
        assert err_open is False

    def test_exception_opens_alert(self):
        with patch("app.callbacks.SessionLocal", return_value=self._mock_session()), \
             patch("app.callbacks.fetch_all_geos", side_effect=RuntimeError("boom")):
            store, status, err_msg, err_open = compute_fetch_and_store(1, "B01001", [2023], _GEO)
        assert err_open is True
        assert "RuntimeError" in err_msg or "boom" in err_msg

    def test_empty_dataframe_opens_alert(self):
        with patch("app.callbacks.SessionLocal", return_value=self._mock_session()), \
             patch("app.callbacks.fetch_all_geos", return_value=pd.DataFrame()):
            store, status, err_msg, err_open = compute_fetch_and_store(1, "B01001", [2023], _GEO)
        assert err_open is True
        assert "No data" in err_msg


# ---------------------------------------------------------------------------
# compute_dim_controls
# ---------------------------------------------------------------------------

def _make_single_dim_store():
    df = _make_long()  # variable_label has no !! → single dim
    return serialise_long(df)


def _make_multi_dim_store():
    df = pd.DataFrame([
        {
            "geoidfq": "050US39049", "name": "Franklin County",
            "reference_period": 2023, "survey": "acs/acs5",
            "concept": "Sex by Age", "universe": "Total population",
            "variable_label": "Total:!!Male:", "variable": "B01001_002",
            "estimate": 640000.0, "moe": 20000.0,
        },
        {
            "geoidfq": "050US39049", "name": "Franklin County",
            "reference_period": 2023, "survey": "acs/acs5",
            "concept": "Sex by Age", "universe": "Total population",
            "variable_label": "Total:!!Female:", "variable": "B01001_026",
            "estimate": 680000.0, "moe": 22000.0,
        },
    ])
    return serialise_long(df)


class TestComputeDimControls:
    def test_no_data_returns_empty_and_hidden(self):
        buttons, style = compute_dim_controls(None, [])
        assert buttons == []
        assert style == {"display": "none"}

    def test_single_dim_returns_no_buttons(self):
        buttons, style = compute_dim_controls(_make_single_dim_store(), [])
        assert buttons == []
        assert style == {"display": "none"}

    def test_multi_dim_returns_drop_buttons(self):
        buttons, style = compute_dim_controls(_make_multi_dim_store(), [])
        assert len(buttons) == 2

    def test_dropped_dim_not_shown_in_buttons(self):
        buttons, _ = compute_dim_controls(_make_multi_dim_store(), ["dim_0"])
        indices = [b.id["index"] for b in buttons]
        assert "dim_0" not in indices

    def test_reset_hidden_when_nothing_dropped(self):
        _, style = compute_dim_controls(_make_multi_dim_store(), [])
        assert style == {"display": "none"}

    def test_reset_visible_when_dim_dropped(self):
        _, style = compute_dim_controls(_make_multi_dim_store(), ["dim_0"])
        assert style == {"display": "inline-block"}


# ---------------------------------------------------------------------------
# compute_dropped_dims
# ---------------------------------------------------------------------------

class TestComputeDroppedDims:
    def test_drop_button_adds_dim(self):
        result = compute_dropped_dims([], None, [], {"type": "drop-dim-btn", "index": "dim_0"})
        assert result == ["dim_0"]

    def test_duplicate_drop_ignored(self):
        result = compute_dropped_dims([], None, ["dim_0"], {"type": "drop-dim-btn", "index": "dim_0"})
        assert result == ["dim_0"]

    def test_reset_clears_all(self):
        result = compute_dropped_dims([], 1, ["dim_0", "dim_1"], "reset-dims-btn")
        assert result == []

    def test_new_data_clears_all(self):
        result = compute_dropped_dims([], None, ["dim_0"], "long-data-store")
        assert result == []

    def test_unknown_trigger_returns_unchanged(self):
        result = compute_dropped_dims([], None, ["dim_0"], "some-other-component")
        assert result == ["dim_0"]

    def test_multiple_sequential_drops(self):
        current = compute_dropped_dims([], None, [], {"type": "drop-dim-btn", "index": "dim_0"})
        current = compute_dropped_dims([], None, current, {"type": "drop-dim-btn", "index": "dim_1"})
        assert "dim_0" in current and "dim_1" in current


# ---------------------------------------------------------------------------
# render_chart_from_wide
# ---------------------------------------------------------------------------

def _make_wide_data():
    df = _make_long()
    data, cols = build_wide_table(df, "estimate", False)
    return {"data": data, "columns": cols}


class TestRenderChartFromWide:
    def test_returns_string(self):
        result = render_chart_from_wide(_make_wide_data(), "bar")
        assert isinstance(result, str)

    def test_returns_data_uri_or_empty(self):
        result = render_chart_from_wide(_make_wide_data(), "bar")
        assert result == "" or result.startswith("data:image/png;base64,")

    def test_none_returns_empty(self):
        assert render_chart_from_wide(None, "bar") == ""

    def test_empty_dict_returns_empty(self):
        assert render_chart_from_wide({}, "bar") == ""

    def test_line_type(self):
        result = render_chart_from_wide(_make_wide_data(), "line")
        assert isinstance(result, str)

    def test_point_type(self):
        result = render_chart_from_wide(_make_wide_data(), "point")
        assert isinstance(result, str)

    def test_x_field_series(self):
        result = render_chart_from_wide(_make_wide_data(), "bar", x_field="series", color_field="dimension")
        assert isinstance(result, str)

    def test_invalid_field_falls_back_gracefully(self):
        result = render_chart_from_wide(_make_wide_data(), "bar", x_field="nonexistent", color_field="also_bad")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# render_chart_image
# ---------------------------------------------------------------------------

class TestRenderChartImage:
    def test_returns_string(self):
        df = _make_long()
        result = render_chart_image(df, "variable_label", "estimate", "reference_period", "bar")
        assert isinstance(result, str)

    def test_returns_data_uri_or_empty(self):
        df = _make_long()
        result = render_chart_image(df, "variable_label", "estimate", "reference_period", "bar")
        assert result == "" or result.startswith("data:image/png;base64,")

    def test_line_chart_type(self):
        df = _make_long()
        result = render_chart_image(df, "reference_period", "estimate", "variable_label", "line")
        assert isinstance(result, str)

    def test_point_chart_type(self):
        df = _make_long()
        result = render_chart_image(df, "variable_label", "estimate", "name", "point")
        assert isinstance(result, str)
