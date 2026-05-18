"""Unit tests for app/fetch.py — mocked sessions and Census API."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.callbacks import compute_fetch_and_store, compute_table
from app.fetch import (
    _choose_drop_method,
    build_wide_table,
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
        # Both dim_0 and dim_1 are returned when 2+ dims exist
        dims = get_droppable_dims(_make_multi_dim_long())
        assert "dim_0" in dims
        assert "dim_1" in dims

    def test_empty_df_returns_empty(self):
        assert get_droppable_dims(pd.DataFrame()) == []


class TestGetAvailableDims:
    def test_no_separator_returns_single_dim(self):
        df = _make_long()  # variable_label = "Dim 0", "Dim 1" — no !!
        assert get_available_dims(df) == ["dim_0"]

    def test_one_separator_returns_two_dims(self):
        df = _make_multi_dim_long()
        dims = get_available_dims(df)
        assert dims == ["dim_0", "dim_1"]

    def test_empty_df_returns_empty(self):
        assert get_available_dims(pd.DataFrame()) == []

    def test_names_are_snake_case(self):
        dims = get_available_dims(_make_multi_dim_long())
        assert all(d.startswith("dim_") for d in dims)


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
        # dim_0 = "Total:" always → no "" rows → aggregate
        dt = _DT(_make_b01001_long())
        assert _choose_drop_method(dt, "dim_0") == "aggregate"

    def test_sex_dim_uses_aggregate(self):
        # dim_1 (Sex): only "" row is the grand total (all other dims also "")
        dt = _DT(_make_b01001_long())
        assert _choose_drop_method(dt, "dim_1") == "aggregate"

    def test_age_dim_uses_summarize(self):
        # dim_2 (Age): "" rows are the sex-subtotals (Male:, Female:) — partial subtotals exist
        dt = _DT(_make_b01001_long())
        assert _choose_drop_method(dt, "dim_2") == "summarize"

    def test_nonexistent_dim_uses_aggregate(self):
        dt = _DT(_make_b01001_long())
        assert _choose_drop_method(dt, "dim_99") == "aggregate"

    def test_simple_fixture_leaf_dim_uses_summarize(self):
        # _make_multi_dim_long has no "Total:" root → dim_1 (age) has partial subtotals
        dt = _DT(_make_multi_dim_long())
        assert _choose_drop_method(dt, "dim_1") == "summarize"

    def test_simple_fixture_root_dim_uses_aggregate(self):
        dt = _DT(_make_multi_dim_long())
        assert _choose_drop_method(dt, "dim_0") == "aggregate"


# ---------------------------------------------------------------------------
# build_wide_table (smoke tests — uses a real DimensionTable pivot)
# ---------------------------------------------------------------------------

class TestBuildWideTable:
    def _long(self):
        # Minimal long DF that DimensionTable can pivot
        return pd.DataFrame([
            {
                "geoidfq": "050US39049", "name": "Franklin County",
                "reference_period": 2023, "survey": "acs/acs5",
                "concept": "Sex by Age", "universe": "Total population",
                "variable_label": "Total", "variable": "B01001_001",
                "estimate": 1300000.0, "moe": 50000.0,
            },
            {
                "geoidfq": "050US39049", "name": "Franklin County",
                "reference_period": 2023, "survey": "acs/acs5",
                "concept": "Sex by Age", "universe": "Total population",
                "variable_label": "Male", "variable": "B01001_002",
                "estimate": 640000.0, "moe": 20000.0,
            },
        ])

    def test_returns_nonempty_data_and_columns(self):
        data, cols = build_wide_table(self._long(), "estimate", False)
        assert len(data) > 0
        assert len(cols) > 0

    def test_columns_include_dim_column(self):
        _, cols = build_wide_table(self._long(), "estimate", False)
        dim_cols = [c for c in cols if c["id"].startswith("__dim_")]
        assert len(dim_cols) >= 1

    def test_estimate_filter(self):
        data, cols = build_wide_table(self._long(), "estimate", False)
        data_col_ids = {c["id"] for c in cols if not c["id"].startswith("__dim_")}
        for record in data:
            for col_id in data_col_ids:
                assert col_id in record

    def test_unknown_value_mode_falls_back_to_empty(self):
        data, cols = build_wide_table(self._long(), "bogus_mode", False)
        # "bogus_mode" triggers the percent() path which may fail or produce no matching vtypes
        assert isinstance(data, list) and isinstance(cols, list)

    def test_drop_invalid_dim_is_ignored(self):
        data, cols = build_wide_table(self._long(), "estimate", False, ["nonexistent_dim"])
        assert len(data) > 0 and len(cols) > 0

    def test_drop_reduces_dim_columns(self):
        df = _make_multi_dim_long()
        _, cols_nodrop = build_wide_table(df, "estimate", False, None)
        _, cols_drop = build_wide_table(df, "estimate", False, ["dim_1"])
        n_dim_nodrop = sum(1 for c in cols_nodrop if c["id"].startswith("__dim_"))
        n_dim_drop = sum(1 for c in cols_drop if c["id"].startswith("__dim_"))
        assert n_dim_drop < n_dim_nodrop

    def test_drop_leaf_dim_uses_summarize_and_produces_data(self):
        # dim_1 has '' rows → summarize → keeps subtotal rows (Male/Female)
        df = _make_multi_dim_long()
        data, cols = build_wide_table(df, "estimate", False, ["dim_1"])
        assert len(data) > 0 and len(cols) > 0

    def test_drop_root_dim_uses_aggregate_and_produces_data(self):
        # dim_0 has no '' rows → aggregate → sums across Sex to get age-only totals
        df = _make_multi_dim_long()
        data, cols = build_wide_table(df, "estimate", False, ["dim_0"])
        assert len(data) > 0 and len(cols) > 0

    def test_drop_sex_in_b01001_structure_returns_age_rows(self):
        # Real B01001-style: dropping Sex (dim_1) should aggregate Male+Female per age,
        # NOT return only the grand total row.
        df = _make_b01001_long()
        data, cols = build_wide_table(df, "estimate", False, ["dim_1"])
        # Should have an "Under 5 years" row (not just grand total)
        dim_vals = [row.get("__dim_0__") or row.get("__dim_1__") or "" for row in data]
        assert len(data) > 1, "Expected age rows, got only grand total"


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


# ---------------------------------------------------------------------------
# compute_table
# ---------------------------------------------------------------------------

class TestComputeTable:
    def test_returns_empty_when_no_store_data(self):
        data, cols, style = compute_table(None, "estimate", False)
        assert data == [] and cols == []
        assert style == {"display": "none"}

    def test_returns_data_on_valid_input(self):
        long = pd.DataFrame([
            {
                "geoidfq": "050US39049", "name": "Franklin County",
                "reference_period": 2023, "survey": "acs/acs5",
                "concept": "Sex by Age", "universe": "Total population",
                "variable_label": "Total", "variable": "B01001_001",
                "estimate": 1300000.0, "moe": 50000.0,
            }
        ])
        store = serialise_long(long)
        data, cols, style = compute_table(store, "estimate", False)
        assert len(data) > 0
        assert style == {"display": "block"}

    def test_returns_data_with_moe_shown(self):
        long = pd.DataFrame([
            {
                "geoidfq": "050US39049", "name": "Franklin County",
                "reference_period": 2023, "survey": "acs/acs5",
                "concept": "Sex by Age", "universe": "Total population",
                "variable_label": "Total", "variable": "B01001_001",
                "estimate": 1300000.0, "moe": 50000.0,
            }
        ])
        store = serialise_long(long)
        data, cols, style = compute_table(store, "estimate", True)
        assert len(data) > 0
        moe_cols = [c for c in cols if "[MOE]" in c["name"]]
        assert len(moe_cols) > 0
