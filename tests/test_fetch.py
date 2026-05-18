"""Unit tests for app/fetch.py — mocked sessions and Census API."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.callbacks import compute_fetch_and_store, compute_table
from app.fetch import (
    build_wide_table,
    deserialise_long,
    fetch_all_geos,
    fetch_all_vintages,
    fetch_long_for_vintage,
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
        data, cols = build_wide_table(self._long(), ["estimate"])
        assert len(data) > 0
        assert len(cols) > 0

    def test_columns_include_dim_column(self):
        _, cols = build_wide_table(self._long(), ["estimate"])
        dim_cols = [c for c in cols if c["id"].startswith("__dim_")]
        assert len(dim_cols) >= 1

    def test_estimate_filter(self):
        data, cols = build_wide_table(self._long(), ["estimate"])
        data_col_ids = {c["id"] for c in cols if not c["id"].startswith("__dim_")}
        for record in data:
            for col_id in data_col_ids:
                assert col_id in record

    def test_empty_value_types_returns_empty(self):
        data, cols = build_wide_table(self._long(), ["percent_estimate"])
        # percent_estimate is not in the fixture — should produce an empty table
        assert data == [] and cols == []


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
        data, cols, style = compute_table(None, ["estimate"])
        assert data == [] and cols == []
        assert style == {"display": "none"}

    def test_returns_empty_when_no_value_types(self):
        store = serialise_long(_make_long())
        data, cols, style = compute_table(store, [])
        assert data == [] and cols == []
        assert style == {"display": "block"}  # card stays visible so user can re-check

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
        data, cols, style = compute_table(store, ["estimate"])
        assert len(data) > 0
        assert style == {"display": "block"}
