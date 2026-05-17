"""Unit tests for cache read/write helpers (session is mocked — no live DB required)."""

from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from app.cache import get_census_long, get_geometry, put_census_long, put_geometry
from app.models import CensusLongRow, GeometryCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KEY = dict(survey="acs/acs5", vintage=2023, group_code="B01001", scope="franklin", sumlevel="140")


def _make_session(rows=None):
    session = MagicMock()
    session.query.return_value.filter_by.return_value.all.return_value = rows or []
    return session


def _make_long_row(**overrides):
    row = MagicMock(spec=CensusLongRow)
    row.geoidfq = "14000US39049001100"
    row.name = "Census Tract 11"
    row.vintage = 2023
    row.survey = "acs/acs5"
    row.concept = "Sex by Age"
    row.universe = "Total population"
    row.variable_label = "Total"
    row.variable = "B01001_001"
    row.estimate = 4234.0
    row.moe = 100.0
    row.percent_estimate = None
    row.percent_moe = None
    row.total_val = None
    row.__dict__.update(overrides)
    return row


# ---------------------------------------------------------------------------
# get_census_long
# ---------------------------------------------------------------------------

class TestGetCensusLong:
    def test_returns_none_when_cache_empty(self):
        session = _make_session(rows=[])
        assert get_census_long(session, **_KEY) is None

    def test_returns_dataframe_for_cached_rows(self):
        session = _make_session(rows=[_make_long_row()])
        result = get_census_long(session, **_KEY)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    def test_columns_include_reference_period(self):
        session = _make_session(rows=[_make_long_row()])
        result = get_census_long(session, **_KEY)
        assert "reference_period" in result.columns

    def test_estimate_value_preserved(self):
        session = _make_session(rows=[_make_long_row(estimate=9999.0)])
        result = get_census_long(session, **_KEY)
        assert result.iloc[0]["estimate"] == 9999.0

    def test_total_mapped_from_total_val(self):
        session = _make_session(rows=[_make_long_row(total_val=500.0)])
        result = get_census_long(session, **_KEY)
        assert "total" in result.columns
        assert result.iloc[0]["total"] == 500.0

    def test_multiple_rows_returned(self):
        rows = [_make_long_row(variable="B01001_001"), _make_long_row(variable="B01001_002")]
        session = _make_session(rows=rows)
        result = get_census_long(session, **_KEY)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# put_census_long
# ---------------------------------------------------------------------------

class TestPutCensusLong:
    def _make_df(self, **extra):
        data = {
            "geoidfq": "14000US39049001100",
            "name": "Census Tract 11",
            "reference_period": 2023,
            "survey": "acs/acs5",
            "concept": "Sex by Age",
            "universe": "Total population",
            "variable_label": "Total",
            "variable": "B01001_001",
            "estimate": 4234.0,
            "moe": 100.0,
        }
        data.update(extra)
        return pd.DataFrame([data])

    def test_deletes_existing_before_insert(self):
        session = _make_session()
        put_census_long(session, self._make_df(), **_KEY)
        session.query.return_value.filter_by.return_value.delete.assert_called_once()

    def test_adds_one_row_per_dataframe_row(self):
        df = pd.concat([self._make_df(variable="B01001_001"), self._make_df(variable="B01001_002")])
        session = _make_session()
        put_census_long(session, df, **_KEY)
        assert session.add.call_count == 2

    def test_commits_after_insert(self):
        session = _make_session()
        put_census_long(session, self._make_df(), **_KEY)
        session.commit.assert_called_once()

    def test_total_column_mapped_to_total_val(self):
        session = _make_session()
        put_census_long(session, self._make_df(total=77.0), **_KEY)
        added: CensusLongRow = session.add.call_args[0][0]
        assert added.total_val == 77.0


# ---------------------------------------------------------------------------
# get_geometry
# ---------------------------------------------------------------------------

class TestGetGeometry:
    _GEO_KEY = dict(scope="franklin", sumlevel="140")

    def test_returns_none_when_cache_empty(self):
        session = _make_session(rows=[])
        assert get_geometry(session, **self._GEO_KEY) is None

    def test_returns_geodataframe_for_cached_rows(self):
        from shapely.geometry import Point

        row = MagicMock(spec=GeometryCache)
        row.geoidfq = "14000US39049001100"
        row.name = "Census Tract 11"
        row.geom = MagicMock()

        session = _make_session(rows=[row])
        with patch("app.cache.to_shape", return_value=Point(0, 0)):
            import geopandas as gpd
            result = get_geometry(session, **self._GEO_KEY)
        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) == 1

    def test_none_geom_stored_as_none(self):
        row = MagicMock(spec=GeometryCache)
        row.geoidfq = "14000US39049001100"
        row.name = "Census Tract 11"
        row.geom = None

        session = _make_session(rows=[row])
        with patch("app.cache.to_shape"):
            result = get_geometry(session, **self._GEO_KEY)
        assert result.iloc[0]["geometry"] is None


# ---------------------------------------------------------------------------
# put_geometry
# ---------------------------------------------------------------------------

class TestPutGeometry:
    _GEO_KEY = dict(scope="franklin", sumlevel="140")

    def _make_gdf(self):
        import geopandas as gpd
        from shapely.geometry import Point
        return gpd.GeoDataFrame(
            [{"GEOIDFQ": "14000US39049001100", "NAME": "Census Tract 11", "geometry": Point(0, 0)}],
            geometry="geometry",
            crs="EPSG:4326",
        )

    def test_deletes_existing_before_insert(self):
        session = _make_session()
        with patch("app.cache.from_shape", return_value=MagicMock()):
            put_geometry(session, self._make_gdf(), **self._GEO_KEY)
        session.query.return_value.filter_by.return_value.delete.assert_called_once()

    def test_adds_one_row_per_feature(self):
        import geopandas as gpd
        from shapely.geometry import Point
        gdf = gpd.GeoDataFrame(
            [
                {"GEOIDFQ": "14000US39049001100", "NAME": "Tract A", "geometry": Point(0, 0)},
                {"GEOIDFQ": "14000US39049001200", "NAME": "Tract B", "geometry": Point(1, 1)},
            ],
            geometry="geometry",
            crs="EPSG:4326",
        )
        session = _make_session()
        with patch("app.cache.from_shape", return_value=MagicMock()):
            put_geometry(session, gdf, **self._GEO_KEY)
        assert session.add.call_count == 2

    def test_commits_after_insert(self):
        session = _make_session()
        with patch("app.cache.from_shape", return_value=MagicMock()):
            put_geometry(session, self._make_gdf(), **self._GEO_KEY)
        session.commit.assert_called_once()
