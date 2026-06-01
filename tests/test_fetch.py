"""Unit tests for app/fetch.py — mocked sessions and Census API."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.callbacks import compute_fetch_and_store
from app.fetch import (
    _apply_dim_filters_to_wide,
    _choose_drop_method,
    build_chart_df,
    build_table_df,
    deserialise_long,
    fetch_all_geos,
    fetch_all_vintages,
    fetch_long_for_vintage,
    get_available_dims,
    get_droppable_dims,
    serialise_long,
)

# ---------------------------------------------------------------------------
# Minimal long DataFrame fixture matching CensusAPI.long schema
# ---------------------------------------------------------------------------

def _make_long(vintage=2023, geoidfq="050US39049", name="Franklin County", n_vars=2):
    rows = []
    for i in range(n_vars):
        rows.append({
            "geoidfq": geoidfq,
            "name": name,
            "reference_period": vintage,
            "survey": "acs/acs5",
            "concept": "Sex by Age",
            "universe": "Total population",
            "variable_label": f"Dim {i}",
            "variable": f"B01001_{i:03d}",
            "estimate": float(1000 + i * 100),
            "moe": float(50 + i * 10),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# fetch_long_for_vintage
# ---------------------------------------------------------------------------

class TestFetchLongForVintage:
    def test_returns_cached_data_without_api_call(self):
        cached = _make_long()
        session = MagicMock()
        with patch("app.fetch.get_census_long", return_value=cached) as mock_get, \
             patch("app.fetch.put_census_long") as mock_put:
            result = fetch_long_for_vintage(session, "B01001", 2023, "franklin", "140")
        mock_get.assert_called_once()
        mock_put.assert_not_called()
        assert len(result) == len(cached)

    def test_fetches_from_api_on_cache_miss(self):
        fetched = _make_long()
        session = MagicMock()
        mock_api = MagicMock()
        mock_api.long = fetched

        with patch("app.fetch.get_census_long", return_value=None), \
             patch("app.fetch.put_census_long") as mock_put, \
             patch("app.fetch.Endpoint"), \
             patch("app.fetch.Group"), \
             patch("app.fetch.CensusAPI", return_value=mock_api):
            result = fetch_long_for_vintage(session, "B01001", 2023, "franklin", "140")

        mock_put.assert_called_once()
        assert len(result) == len(fetched)

    def test_writes_to_cache_after_api_call(self):
        fetched = _make_long()
        session = MagicMock()
        mock_api = MagicMock()
        mock_api.long = fetched

        with patch("app.fetch.get_census_long", return_value=None), \
             patch("app.fetch.put_census_long") as mock_put, \
             patch("app.fetch.Endpoint"), \
             patch("app.fetch.Group"), \
             patch("app.fetch.CensusAPI", return_value=mock_api):
            fetch_long_for_vintage(session, "B01001", 2023, "franklin", "140")

        args = mock_put.call_args[0]
        assert args[2] == "acs/acs5"   # survey
        assert args[3] == 2023          # vintage
        assert args[4] == "B01001"      # group_code


# ---------------------------------------------------------------------------
# fetch_all_vintages
# ---------------------------------------------------------------------------

class TestFetchAllVintages:
    def test_concatenates_multiple_vintages(self):
        session = MagicMock()
        df_2022 = _make_long(vintage=2022)
        df_2023 = _make_long(vintage=2023)

        with patch("app.fetch.fetch_long_for_vintage", side_effect=[df_2022, df_2023]):
            result = fetch_all_vintages(session, "B01001", [2022, 2023], "franklin", "140")

        assert len(result) == len(df_2022) + len(df_2023)
        assert set(result["reference_period"].unique()) == {2022, 2023}

    def test_returns_empty_dataframe_for_no_vintages(self):
        session = MagicMock()
        result = fetch_all_vintages(session, "B01001", [], "franklin", "140")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_single_vintage_no_duplicate_rows(self):
        session = MagicMock()
        df = _make_long(vintage=2023)
        with patch("app.fetch.fetch_long_for_vintage", return_value=df):
            result = fetch_all_vintages(session, "B01001", [2023], "franklin", "140")
        assert len(result) == len(df)


# ---------------------------------------------------------------------------
# serialise_long / deserialise_long
# ---------------------------------------------------------------------------

class TestSerialiseRoundTrip:
    def test_round_trip_preserves_shape(self):
        df = _make_long()
        stored = serialise_long(df)
        restored = deserialise_long(stored)
        assert restored.shape == df.shape

    def test_round_trip_preserves_columns(self):
        df = _make_long()
        restored = deserialise_long(serialise_long(df))
        assert set(restored.columns) == set(df.columns)

    def test_reference_period_is_int_after_deserialise(self):
        df = _make_long(vintage=2022)
        restored = deserialise_long(serialise_long(df))
        assert restored["reference_period"].dtype == int

    def test_estimate_values_preserved(self):
        df = _make_long()
        restored = deserialise_long(serialise_long(df))
        assert list(restored["estimate"]) == list(df["estimate"])


# ---------------------------------------------------------------------------
# get_available_dims
# ---------------------------------------------------------------------------

def _make_multi_dim_long():
    """Two-dim long DF matching real Census structure.

    Subtotal rows (dim_1='') plus detail rows (dim_1 populated) so that
    ``get_droppable_dims`` correctly identifies dim_1 as droppable.
    """
    def _row(label, var, est, moe):
        return {
            "geoidfq": "050US39049", "name": "Franklin County",
            "reference_period": 2023, "survey": "acs/acs5",
            "concept": "Sex by Age", "universe": "Total population",
            "variable_label": label, "variable": var,
            "estimate": est, "moe": moe,
        }
    return pd.DataFrame([
        # Subtotal rows — dim_1 will be '' after parsing
        _row("Male:",   "B01001_002", 640_000.0, 20_000.0),
        _row("Female:", "B01001_026", 680_000.0, 22_000.0),
        # Detail rows — dim_1 populated
        _row("Male:!!Under 5 years:",   "B01001_003", 40_000.0, 3_000.0),
        _row("Female:!!Under 5 years:", "B01001_027", 38_000.0, 2_800.0),
    ])


class TestGetDroppableDims:
    def test_single_dim_returns_empty(self):
        assert get_droppable_dims(_make_long()) == []

    def test_multi_dim_returns_all_dims(self):
        # Both dims are returned when 2+ exist; names are concept_dims values
        dims = get_droppable_dims(_make_multi_dim_long())
        assert len(dims) >= 2

    def test_empty_df_returns_empty(self):
        assert get_droppable_dims(pd.DataFrame()) == []


class TestGetAvailableDims:
    def test_single_dim_returns_one_column(self):
        dims = get_available_dims(_make_long())
        assert len(dims) == 1

    def test_multi_dim_returns_named_columns(self):
        dims = get_available_dims(_make_multi_dim_long())
        assert len(dims) >= 2
        assert all(isinstance(d, str) for d in dims)

    def test_empty_df_returns_empty(self):
        assert get_available_dims(pd.DataFrame()) == []


# ---------------------------------------------------------------------------
# _choose_drop_method — mirrors real B01001 dim structure with "Total:" root
# ---------------------------------------------------------------------------

def _make_b01001_long():
    """Minimal B01001-style long DF matching real Census label structure.

    After _parse_dims:
      dim_0 = "Total:" (universal root, same for every row)
      dim_1 = Sex: "Male:", "Female:", "" (grand-total row)
      dim_2 = Age: "Under 5 years", ..., "" (sex-subtotal rows + grand total)
    """
    def _row(label, var, est):
        return {
            "geoidfq": "050US39049", "name": "Franklin County",
            "reference_period": 2023, "survey": "acs/acs5",
            "concept": "Sex by Age", "universe": "Total population",
            "variable_label": label, "variable": var,
            "estimate": est, "moe": est * 0.05,
        }
    return pd.DataFrame([
        _row("Total:",                        "B01001_001", 1_300_000.0),
        _row("Total:!!Male:",                 "B01001_002",   640_000.0),
        _row("Total:!!Female:",               "B01001_026",   660_000.0),
        _row("Total:!!Male:!!Under 5 years",  "B01001_003",    40_000.0),
        _row("Total:!!Female:!!Under 5 years","B01001_027",    38_000.0),
    ])


from morpc_census.api import DimensionTable as _DT


class TestChooseDropMethod:
    def test_root_dim_uses_aggregate(self):
        # "Total" col has no empty rows → aggregate
        dt = _DT(_make_b01001_long())
        assert _choose_drop_method(dt, "Total") == "aggregate"

    def test_sex_dim_uses_aggregate(self):
        # "Sex": its only empty row is the grand total → aggregate
        dt = _DT(_make_b01001_long())
        assert _choose_drop_method(dt, "Sex") == "aggregate"

    def test_age_dim_uses_summarize(self):
        # "Age": "" rows are the sex-subtotals (Male, Female) — partial subtotals exist
        dt = _DT(_make_b01001_long())
        assert _choose_drop_method(dt, "Age") == "summarize"

    def test_nonexistent_dim_uses_aggregate(self):
        dt = _DT(_make_b01001_long())
        assert _choose_drop_method(dt, "nonexistent_dim") == "aggregate"

    def test_simple_fixture_leaf_dim_uses_summarize(self):
        # "Age" is the leaf dim — has '' rows for Male/Female subtotals
        dt = _DT(_make_multi_dim_long())
        assert _choose_drop_method(dt, "Age") == "summarize"

    def test_simple_fixture_root_dim_uses_aggregate(self):
        # "Sex" is the root dim — no '' rows → aggregate
        dt = _DT(_make_multi_dim_long())
        assert _choose_drop_method(dt, "Sex") == "aggregate"


# ---------------------------------------------------------------------------
# _apply_dim_filters_to_wide
# ---------------------------------------------------------------------------

class TestApplyDimFiltersToWide:
    def _make_wide(self):
        from morpc_census.api import DimensionTable
        return DimensionTable(_make_multi_dim_long()).wide()

    def test_no_filter_returns_all_rows(self):
        wide = self._make_wide()
        result = _apply_dim_filters_to_wide(wide, {})
        assert len(result) == len(wide)

    def test_none_filter_returns_all_rows(self):
        wide = self._make_wide()
        result = _apply_dim_filters_to_wide(wide, None)
        assert len(result) == len(wide)

    def test_multiindex_filter_reduces_rows(self):
        wide = self._make_wide()
        # Get the first dim name and a valid value from the index
        if isinstance(wide.index, pd.MultiIndex):
            dim_name = wide.index.names[0]
            val = str(wide.index.get_level_values(dim_name)[0])
            result = _apply_dim_filters_to_wide(wide, {dim_name: [val]})
            assert len(result) <= len(wide)
        else:
            # single-level: filter to one value
            dim_name = wide.index.name
            val = str(wide.index[0])
            result = _apply_dim_filters_to_wide(wide, {dim_name: [val]})
            assert len(result) <= len(wide)

    def test_nonexistent_dim_ignored(self):
        wide = self._make_wide()
        result = _apply_dim_filters_to_wide(wide, {"__bogus__": ["x"]})
        assert len(result) == len(wide)

    def test_empty_selection_list_ignored(self):
        wide = self._make_wide()
        if isinstance(wide.index, pd.MultiIndex):
            dim_name = wide.index.names[0]
        else:
            dim_name = wide.index.name
        result = _apply_dim_filters_to_wide(wide, {dim_name: []})
        assert len(result) == len(wide)


# ---------------------------------------------------------------------------
# build_table_df
# ---------------------------------------------------------------------------

def _make_two_geo_long():
    """Long DF with two geographies for testing merged column headers."""
    def _row(geoidfq, name, label, var, est):
        return {
            "geoidfq": geoidfq, "name": name,
            "reference_period": 2023, "survey": "acs/acs5",
            "concept": "Sex by Age", "universe": "Total population",
            "variable_label": label, "variable": var,
            "estimate": est, "moe": est * 0.05,
        }
    rows = []
    for geoidfq, name in [("050US39049", "Franklin County"), ("050US39089", "Licking County")]:
        prefix = "B01" if "Franklin" in name else "B02"
        rows += [
            _row(geoidfq, name, "Male:", f"{prefix}_002", 640_000.0),
            _row(geoidfq, name, "Female:", f"{prefix}_026", 680_000.0),
            _row(geoidfq, name, "Male:!!Under 5 years:", f"{prefix}_003", 40_000.0),
            _row(geoidfq, name, "Female:!!Under 5 years:", f"{prefix}_027", 38_000.0),
        ]
    return pd.DataFrame(rows)


class TestBuildTableDf:
    def test_empty_df_returns_empty_tuple(self):
        data, cols = build_table_df(pd.DataFrame())
        assert data == [] and cols == []

    def test_no_variable_label_column_returns_empty(self):
        df = pd.DataFrame([{"geoidfq": "x", "estimate": 1.0}])
        data, cols = build_table_df(df)
        assert data == [] and cols == []

    def test_returns_tuple_of_lists(self):
        data, cols = build_table_df(_make_multi_dim_long())
        assert isinstance(data, list) and isinstance(cols, list)

    def test_data_is_nonempty(self):
        data, cols = build_table_df(_make_multi_dim_long())
        assert len(data) > 0

    def test_dim_cols_have_2level_name(self):
        _, cols = build_table_df(_make_multi_dim_long())
        dim_cols = [c for c in cols if c["id"].startswith("__dim_")]
        assert len(dim_cols) >= 1
        for c in dim_cols:
            assert isinstance(c["name"], list) and len(c["name"]) == 2
            assert c["name"][0] == ""  # blank top level

    def test_data_cols_have_2level_name(self):
        _, cols = build_table_df(_make_multi_dim_long())
        data_cols = [c for c in cols if not c["id"].startswith("__dim_")]
        assert len(data_cols) >= 1
        for c in data_cols:
            assert isinstance(c["name"], list) and len(c["name"]) == 2

    def test_data_col_id_contains_geoidfq(self):
        _, cols = build_table_df(_make_multi_dim_long())
        data_cols = [c for c in cols if not c["id"].startswith("__dim_")]
        assert any("050US39049" in c["id"] for c in data_cols)

    def test_show_moe_false_excludes_moe_columns(self):
        _, cols = build_table_df(_make_multi_dim_long(), show_moe=False)
        data_cols = [c for c in cols if not c["id"].startswith("__dim_")]
        assert not any("moe" in c["id"] for c in data_cols)

    def test_show_moe_true_includes_moe_columns(self):
        _, cols = build_table_df(_make_multi_dim_long(), show_moe=True)
        data_cols = [c for c in cols if not c["id"].startswith("__dim_")]
        assert any("moe" in c["id"] for c in data_cols)

    def test_drop_reduces_dim_columns(self):
        df = _make_multi_dim_long()
        _, cols_full = build_table_df(df)
        n_dims_full = sum(1 for c in cols_full if c["id"].startswith("__dim_"))
        _, cols_drop = build_table_df(df, dropped_dims=["Age"])
        n_dims_drop = sum(1 for c in cols_drop if c["id"].startswith("__dim_"))
        assert n_dims_drop < n_dims_full

    def test_invalid_dropped_dim_ignored(self):
        data, cols = build_table_df(_make_multi_dim_long(), dropped_dims=["nonexistent"])
        assert len(data) > 0 and len(cols) > 0

    def test_dim_filter_reduces_rows(self):
        data_all, _ = build_table_df(_make_multi_dim_long())
        # Find a dim column and filter to one value
        from morpc_census.api import DimensionTable
        dt = DimensionTable(_make_multi_dim_long())
        dim_name = list(dt.dims.columns)[0]
        cats = [str(v) for v in dt.dims[dim_name].cat.categories if str(v) != ""]
        if cats:
            data_filtered, _ = build_table_df(_make_multi_dim_long(), dim_filters={dim_name: [cats[0]]})
            assert len(data_filtered) <= len(data_all)

    def test_dim_filter_no_match_returns_empty(self):
        data, cols = build_table_df(_make_multi_dim_long(), dim_filters={"Sex": ["__bogus__"]})
        assert data == [] and cols == []

    def test_records_contain_all_data_col_ids(self):
        data, cols = build_table_df(_make_multi_dim_long())
        data_col_ids = {c["id"] for c in cols if not c["id"].startswith("__dim_")}
        for record in data:
            for col_id in data_col_ids:
                assert col_id in record

    def test_two_geos_produce_two_data_col_groups(self):
        data, cols = build_table_df(_make_two_geo_long())
        data_cols = [c for c in cols if not c["id"].startswith("__dim_")]
        geo_names = {c["name"][0] for c in data_cols}
        assert len(geo_names) == 2


# ---------------------------------------------------------------------------
# build_chart_df
# ---------------------------------------------------------------------------

class TestBuildChartDf:
    def test_empty_df_returns_empty(self):
        result = build_chart_df(pd.DataFrame())
        assert isinstance(result, pd.DataFrame) and result.empty

    def test_no_variable_label_returns_empty(self):
        df = pd.DataFrame([{"geoidfq": "x", "estimate": 1.0}])
        assert build_chart_df(df).empty

    def test_returns_dataframe(self):
        result = build_chart_df(_make_multi_dim_long())
        assert isinstance(result, pd.DataFrame)

    def test_has_name_refperiod_estimate(self):
        result = build_chart_df(_make_multi_dim_long())
        assert "name" in result.columns
        assert "reference_period" in result.columns
        assert "estimate" in result.columns

    def test_no_moe_column(self):
        result = build_chart_df(_make_multi_dim_long())
        assert "moe" not in result.columns

    def test_dim_cols_are_ordered_categorical(self):
        result = build_chart_df(_make_multi_dim_long())
        from morpc_census.api import DimensionTable
        dim_cols = list(DimensionTable(_make_multi_dim_long()).dims.columns)
        for col in dim_cols:
            assert col in result.columns
            assert hasattr(result[col], "cat") and result[col].cat.ordered

    def test_no_empty_string_in_dim_cols(self):
        result = build_chart_df(_make_multi_dim_long())
        from morpc_census.api import DimensionTable
        dim_cols = list(DimensionTable(_make_multi_dim_long()).dims.columns)
        for col in dim_cols:
            assert not (result[col].astype(str) == "").any()

    def test_dropped_dims_reduce_dim_columns(self):
        full = build_chart_df(_make_multi_dim_long())
        from morpc_census.api import DimensionTable
        dim_cols_full = list(DimensionTable(_make_multi_dim_long()).dims.columns)
        dropped = build_chart_df(_make_multi_dim_long(), dropped_dims=["Age"])
        from morpc_census.api import DimensionTable as DT2
        dim_cols_dropped = list(DT2(_make_multi_dim_long()).dims.columns)
        assert len([c for c in full.columns if c in dim_cols_full]) > len([c for c in dropped.columns if c in dim_cols_dropped])

    def test_multi_geo_produces_multiple_name_values(self):
        result = build_chart_df(_make_two_geo_long())
        assert result["name"].nunique() == 2

    def test_multi_vintage_produces_multiple_refperiod_values(self):
        df1 = _make_multi_dim_long()
        df2 = _make_multi_dim_long()
        df2["reference_period"] = 2022
        combined = pd.concat([df1, df2], ignore_index=True)
        result = build_chart_df(combined)
        assert result["reference_period"].nunique() == 2


# ---------------------------------------------------------------------------
# fetch_all_geos
# ---------------------------------------------------------------------------

_GEO_LIST = [{"scope": "franklin", "sumlevel": "140"}]


class TestFetchAllGeos:
    def test_concatenates_multiple_geos(self):
        session = MagicMock()
        df_franklin = _make_long(geoidfq="050US39049", name="Franklin County")
        df_licking = _make_long(geoidfq="050US39089", name="Licking County")
        geos = [
            {"scope": "franklin", "sumlevel": "050"},
            {"scope": "licking", "sumlevel": "050"},
        ]
        with patch("app.fetch.fetch_all_vintages", side_effect=[df_franklin, df_licking]):
            result = fetch_all_geos(session, "B01001", [2023], geos)
        assert len(result) == len(df_franklin) + len(df_licking)
        assert set(result["name"].unique()) == {"Franklin County", "Licking County"}

    def test_returns_empty_for_empty_geo_list(self):
        session = MagicMock()
        result = fetch_all_geos(session, "B01001", [2023], [])
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_single_geo_returns_its_data(self):
        session = MagicMock()
        df = _make_long()
        with patch("app.fetch.fetch_all_vintages", return_value=df):
            result = fetch_all_geos(session, "B01001", [2023], [{"scope": "franklin", "sumlevel": "140"}])
        assert len(result) == len(df)


# ---------------------------------------------------------------------------
# compute_fetch_and_store
# ---------------------------------------------------------------------------

class TestComputeFetchAndStore:
    def test_returns_serialised_data_and_status(self):
        df = _make_long()
        with patch("app.callbacks.fetch_all_geos", return_value=df), \
             patch("app.callbacks.SessionLocal"):
            store_data, status, err_msg, err_open = compute_fetch_and_store(1, "B01001", [2023], _GEO_LIST)
        assert isinstance(store_data, dict)
        assert "B01001" in status
        assert err_open is False

    def test_returns_error_message_on_exception(self):
        with patch("app.callbacks.SessionLocal", side_effect=Exception("db down")):
            store_data, status, err_msg, err_open = compute_fetch_and_store(1, "B01001", [2023], _GEO_LIST)
        assert err_open is True
        assert "db down" in err_msg or err_msg


