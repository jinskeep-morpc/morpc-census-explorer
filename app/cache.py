"""Cache read/write helpers for census data and geometry."""

from __future__ import annotations

from typing import Optional

import pandas as pd
from geoalchemy2.shape import from_shape, to_shape
from sqlalchemy.orm import Session

from app.models import CensusLongRow, GeometryCache

# Columns from CensusAPI.long that map to nullable float DB columns.
_VALUE_COLS = ("estimate", "moe", "percent_estimate", "percent_moe")


def get_census_long(
    session: Session,
    survey: str,
    vintage: int,
    group_code: str,
    scope: str,
    sumlevel: str,
) -> pd.DataFrame | None:
    """Return cached long DataFrame for the given query key, or None if not cached."""
    rows = (
        session.query(CensusLongRow)
        .filter_by(survey=survey, vintage=vintage, group_code=group_code, scope=scope, sumlevel=sumlevel)
        .all()
    )
    if not rows:
        return None
    records = [
        {
            "geoidfq": r.geoidfq,
            "name": r.name,
            "reference_period": r.vintage,
            "survey": r.survey,
            "concept": r.concept,
            "universe": r.universe,
            "variable_label": r.variable_label,
            "variable": r.variable,
            "estimate": r.estimate,
            "moe": r.moe,
            "percent_estimate": r.percent_estimate,
            "percent_moe": r.percent_moe,
            "total": r.total_val,
        }
        for r in rows
    ]
    return pd.DataFrame(records)


def put_census_long(
    session: Session,
    df: pd.DataFrame,
    survey: str,
    vintage: int,
    group_code: str,
    scope: str,
    sumlevel: str,
) -> None:
    """Write a CensusAPI.long DataFrame to cache, replacing any existing rows for the key."""
    session.query(CensusLongRow).filter_by(
        survey=survey, vintage=vintage, group_code=group_code, scope=scope, sumlevel=sumlevel
    ).delete()
    for _, row in df.iterrows():
        session.add(
            CensusLongRow(
                survey=survey,
                vintage=vintage,
                group_code=group_code,
                scope=scope,
                sumlevel=sumlevel,
                geoidfq=row["geoidfq"],
                name=row.get("name"),
                concept=row.get("concept"),
                universe=row.get("universe"),
                variable_label=row.get("variable_label", ""),
                variable=row["variable"],
                estimate=row.get("estimate"),
                moe=row.get("moe"),
                percent_estimate=row.get("percent_estimate"),
                percent_moe=row.get("percent_moe"),
                total_val=row.get("total"),
            )
        )
    session.commit()


def get_geometry(
    session: Session,
    scope: str,
    sumlevel: str,
    vintage: Optional[int] = None,
) -> "gpd.GeoDataFrame | None":
    """Return cached geometry for the given scope/sumlevel/vintage, or None if not cached."""
    import geopandas as gpd

    rows = (
        session.query(GeometryCache)
        .filter_by(scope=scope, sumlevel=sumlevel, vintage=vintage)
        .all()
    )
    if not rows:
        return None
    records = [
        {
            "geoidfq": r.geoidfq,
            "name": r.name,
            "geometry": to_shape(r.geom) if r.geom is not None else None,
        }
        for r in rows
    ]
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")


def put_geometry(
    session: Session,
    gdf: "gpd.GeoDataFrame",
    scope: str,
    sumlevel: str,
    vintage: Optional[int] = None,
) -> None:
    """Write a GeoDataFrame from fetch_geos_from_scope_sumlevel to cache."""
    session.query(GeometryCache).filter_by(scope=scope, sumlevel=sumlevel, vintage=vintage).delete()

    geoidfq_col = "GEOIDFQ" if "GEOIDFQ" in gdf.columns else "geoidfq"
    name_col = next((c for c in ("NAME", "name") if c in gdf.columns), None)

    for _, row in gdf.iterrows():
        geom = from_shape(row.geometry, srid=4326) if row.geometry is not None else None
        session.add(
            GeometryCache(
                scope=scope,
                sumlevel=sumlevel,
                vintage=vintage,
                geoidfq=row[geoidfq_col],
                name=row[name_col] if name_col else None,
                geom=geom,
            )
        )
    session.commit()
