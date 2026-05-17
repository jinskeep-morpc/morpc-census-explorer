"""Smoke tests: models and cache helpers import and are structurally correct."""

from app.models import CensusLongRow, GeometryCache


def test_census_long_row_tablename():
    assert CensusLongRow.__tablename__ == "census_long"


def test_census_long_row_columns():
    cols = {c.name for c in CensusLongRow.__table__.columns}
    required = {
        "id", "survey", "vintage", "group_code", "scope", "sumlevel",
        "geoidfq", "name", "concept", "universe", "variable_label", "variable",
        "estimate", "moe", "percent_estimate", "percent_moe", "total_val",
    }
    assert required <= cols


def test_census_long_row_unique_constraint():
    constraint_cols = {
        col.name
        for c in CensusLongRow.__table__.constraints
        if hasattr(c, "columns")
        for col in c.columns
        if c.name == "uq_census_long_row"
    }
    assert "survey" in constraint_cols
    assert "geoidfq" in constraint_cols
    assert "variable" in constraint_cols


def test_geometry_cache_tablename():
    assert GeometryCache.__tablename__ == "geometry_cache"


def test_geometry_cache_columns():
    cols = {c.name for c in GeometryCache.__table__.columns}
    required = {"id", "scope", "sumlevel", "vintage", "geoidfq", "name", "geom"}
    assert required <= cols


def test_geometry_cache_vintage_nullable():
    col = GeometryCache.__table__.columns["vintage"]
    assert col.nullable
