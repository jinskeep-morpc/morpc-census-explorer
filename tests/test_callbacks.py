"""Unit tests for callback logic in app/callbacks.py."""

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from app.callbacks import (
    _build_chart_title,
    _chart_axis_options_from_long,
    _friendly_error,
    apply_dim_filters,
    compute_dim_controls,
    compute_dim_filter_controls,
    compute_dropped_dims,
    compute_fetch_and_store,
    compute_fetch_button_disabled,
    compute_geo_chips,
    compute_geo_list,
    compute_group_options,
    long_to_chart_df,
    render_chart_from_long,
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


def _make_multi_dim_long():
    """Two-dim long DF with subtotal rows so dim_1 is droppable."""
    def _row(label, var, est, moe):
        return {
            "geoidfq": "050US39049", "name": "Franklin County",
            "reference_period": 2023, "survey": "acs/acs5",
            "concept": "Sex by Age", "universe": "Total population",
            "variable_label": label, "variable": var,
            "estimate": est, "moe": moe,
        }
    return pd.DataFrame([
        _row("Male:",                   "B01001_002", 640_000.0, 20_000.0),
        _row("Female:",                 "B01001_026", 680_000.0, 22_000.0),
        _row("Male:!!Under 5 years:",   "B01001_003",  40_000.0,  3_000.0),
        _row("Female:!!Under 5 years:", "B01001_027",  38_000.0,  2_800.0),
    ])


def _make_multi_dim_store():
    return serialise_long(_make_multi_dim_long())


def _make_multi_dim_wide():
    df = _make_multi_dim_long()
    data, cols = build_wide_table(df, "estimate", False)
    return {"data": data, "columns": cols}


class TestComputeDimControls:
    def test_no_data_returns_empty_and_hidden(self):
        buttons, style = compute_dim_controls(None, [])
        assert buttons == []
        assert style == {"display": "none"}

    def test_single_dim_returns_no_buttons(self):
        # Single-level labels → dim_0 never '' → nothing droppable
        buttons, style = compute_dim_controls(_make_single_dim_store(), [])
        assert buttons == []
        assert style == {"display": "none"}

    def test_multi_dim_returns_drop_buttons_for_all_dims(self):
        # DimensionTable uses concept_dims names; check some buttons exist
        buttons, style = compute_dim_controls(_make_multi_dim_store(), [])
        assert len(buttons) >= 2

    def test_dropped_dim_not_shown_in_buttons(self):
        buttons, _ = compute_dim_controls(_make_multi_dim_store(), ["dim_1"])
        indices = [b.id["index"] for b in buttons]
        assert "dim_1" not in indices

    def test_reset_hidden_when_nothing_dropped(self):
        _, style = compute_dim_controls(_make_multi_dim_store(), [])
        assert style == {"display": "none"}

    def test_reset_visible_when_dim_dropped(self):
        _, style = compute_dim_controls(_make_multi_dim_store(), ["dim_1"])
        assert style == {"display": "inline-block"}


# ---------------------------------------------------------------------------
# compute_dim_filter_controls
# ---------------------------------------------------------------------------

class TestComputeDimFilterControls:
    def test_none_returns_empty(self):
        assert compute_dim_filter_controls(None) == []

    def test_empty_dict_returns_empty(self):
        assert compute_dim_filter_controls({}) == []

    def test_single_dim_with_multiple_values_returns_dropdown(self):
        wide = _make_multi_dim_wide()
        controls = compute_dim_filter_controls(wide)
        # At least one control should be produced for the multi-value dim column
        assert len(controls) >= 1

    def test_dropdown_has_correct_options(self):
        wide = _make_multi_dim_wide()
        controls = compute_dim_filter_controls(wide)
        # Find the dropdown inside the first control (Span → children[1])
        assert controls  # non-empty
        span = controls[0]
        dropdown = span.children[1]
        option_values = {o["value"] for o in dropdown.options}
        # Should contain actual dim values (not empty string)
        assert option_values  # non-empty


# ---------------------------------------------------------------------------
# apply_dim_filters
# ---------------------------------------------------------------------------

class TestApplyDimFilters:
    def test_no_filter_returns_all_rows(self):
        wide = _make_multi_dim_wide()
        data, cols = apply_dim_filters(wide, {})
        assert len(data) == len(wide["data"])

    def test_none_input_returns_empty(self):
        data, cols = apply_dim_filters(None, {})
        assert data == [] and cols == []

    def test_filter_reduces_rows(self):
        wide = _make_multi_dim_wide()
        all_data, cols = apply_dim_filters(wide, {})
        # Get a dim_0 value that exists
        dim0_vals = list({row.get("__dim_0__") for row in wide["data"] if row.get("__dim_0__")})
        if dim0_vals:
            filtered, _ = apply_dim_filters(wide, {"dim_0": [dim0_vals[0]]})
            assert len(filtered) <= len(all_data)

    def test_filter_by_nonexistent_value_returns_empty(self):
        wide = _make_multi_dim_wide()
        data, _ = apply_dim_filters(wide, {"dim_0": ["__does_not_exist__"]})
        assert data == []


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
    def test_returns_dict(self):
        result = render_chart_from_wide(_make_wide_data(), "bar")
        assert isinstance(result, dict)

    def test_returns_nonempty_spec(self):
        result = render_chart_from_wide(_make_wide_data(), "bar")
        assert "$schema" in result

    def test_none_returns_empty_dict(self):
        assert render_chart_from_wide(None, "bar") == {}

    def test_empty_dict_returns_empty_dict(self):
        assert render_chart_from_wide({}, "bar") == {}

    def test_line_type(self):
        result = render_chart_from_wide(_make_wide_data(), "line")
        assert isinstance(result, dict)

    def test_point_type(self):
        result = render_chart_from_wide(_make_wide_data(), "point")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# render_chart_image
# ---------------------------------------------------------------------------

class TestRenderChartImage:
    def test_returns_dict(self):
        df = _make_long()
        result = render_chart_image(df, "variable_label", "estimate", "reference_period", "bar")
        assert isinstance(result, dict)

    def test_returns_nonempty_spec(self):
        df = _make_long()
        result = render_chart_image(df, "variable_label", "estimate", "reference_period", "bar")
        assert "$schema" in result

    def test_line_chart_type(self):
        df = _make_long()
        result = render_chart_image(df, "reference_period", "estimate", "variable_label", "line")
        assert isinstance(result, dict)

    def test_point_chart_type(self):
        df = _make_long()
        result = render_chart_image(df, "variable_label", "estimate", "name", "point")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# long_to_chart_df
# ---------------------------------------------------------------------------

class TestLongToChartDf:
    def test_empty_long_returns_empty(self):
        result = long_to_chart_df(pd.DataFrame())
        assert result.empty

    def test_single_dim_returns_dim_geography_year_value(self):
        result = long_to_chart_df(_make_long())
        assert "geography" in result.columns
        assert "year" in result.columns
        assert "value" in result.columns

    def test_estimate_mode_uses_estimate(self):
        result = long_to_chart_df(_make_long(), value_mode="estimate")
        assert not result.empty
        assert result["value"].iloc[0] == pytest.approx(1_300_000.0)

    def test_multi_dim_has_dim_columns(self):
        result = long_to_chart_df(_make_multi_dim_long())
        # Should have at least one dim column beyond geography/year/value
        dim_cols = [c for c in result.columns if c not in ("geography", "year", "value")]
        assert len(dim_cols) >= 1

    def test_leaf_only_no_subtotals(self):
        result = long_to_chart_df(_make_multi_dim_long())
        # Leaf rows only: no row should have any empty-string dim value
        dim_cols = [c for c in result.columns if c not in ("geography", "year", "value")]
        for col in dim_cols:
            assert not (result[col].astype(str) == "").any()


# ---------------------------------------------------------------------------
# _chart_axis_options_from_long
# ---------------------------------------------------------------------------

class TestChartAxisOptionsFromLong:
    def test_empty_returns_empty(self):
        assert _chart_axis_options_from_long(pd.DataFrame()) == []

    def test_always_includes_value(self):
        chart_df = long_to_chart_df(_make_long())
        options = _chart_axis_options_from_long(chart_df)
        labels = [o["value"] for o in options]
        assert "value" in labels

    def test_includes_geography_and_year(self):
        chart_df = long_to_chart_df(_make_long())
        options = _chart_axis_options_from_long(chart_df)
        values = [o["value"] for o in options]
        assert "geography" in values
        assert "year" in values


# ---------------------------------------------------------------------------
# render_chart_from_long
# ---------------------------------------------------------------------------

class TestRenderChartFromLong:
    def test_empty_df_returns_empty(self):
        assert render_chart_from_long(pd.DataFrame()) == {}

    def test_returns_vega_spec(self):
        chart_df = long_to_chart_df(_make_multi_dim_long())
        result = render_chart_from_long(chart_df, "bar")
        assert isinstance(result, dict)
        assert "$schema" in result

    def test_line_type(self):
        chart_df = long_to_chart_df(_make_multi_dim_long())
        result = render_chart_from_long(chart_df, "line")
        assert "$schema" in result

    def test_invalid_field_falls_back_gracefully(self):
        chart_df = long_to_chart_df(_make_multi_dim_long())
        result = render_chart_from_long(chart_df, "bar", x_field="nonexistent", color_field="also_bad")
        assert isinstance(result, dict)

    def test_title_appears_in_spec(self):
        chart_df = long_to_chart_df(_make_multi_dim_long())
        result = render_chart_from_long(chart_df, "bar", title="Test Title", subtitle="Source: X")
        spec_str = str(result)
        assert "Test Title" in spec_str


# ---------------------------------------------------------------------------
# _build_chart_title
# ---------------------------------------------------------------------------

class TestBuildChartTitle:
    def test_all_parts(self):
        result = _build_chart_title("Sex by Age", [{"scope": "Franklin County"}], [2023])
        assert "Sex by Age" in result
        assert "Franklin County" in result
        assert "2023" in result

    def test_multi_vintage_range(self):
        result = _build_chart_title("Sex by Age", [{"scope": "Franklin County"}], [2021, 2022, 2023])
        assert "2021" in result and "2023" in result

    def test_no_group(self):
        result = _build_chart_title(None, [{"scope": "Franklin County"}], [2023])
        assert "Franklin County" in result

    def test_empty_returns_empty_string(self):
        result = _build_chart_title(None, None, None)
        assert result == ""
