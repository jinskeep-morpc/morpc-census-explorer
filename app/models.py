from __future__ import annotations

from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CensusLongRow(Base):
    """One row of a CensusAPI.long DataFrame, keyed by query parameters."""

    __tablename__ = "census_long"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Cache key
    survey: Mapped[str] = mapped_column(String(50))
    vintage: Mapped[int] = mapped_column(Integer)
    group_code: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(50))
    sumlevel: Mapped[str] = mapped_column(String(10))
    # Row data
    geoidfq: Mapped[str] = mapped_column(String(50))
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    concept: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    universe: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    variable_label: Mapped[str] = mapped_column(String(500))
    variable: Mapped[str] = mapped_column(String(30))
    estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    moe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percent_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percent_moe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 'total' is a SQL keyword in some dialects; use total_val
    total_val: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "survey", "vintage", "group_code", "scope", "sumlevel", "geoidfq", "variable",
            name="uq_census_long_row",
        ),
    )


class GeometryCache(Base):
    """Cached TIGERweb boundary geometry keyed by query parameters."""

    __tablename__ = "geometry_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Cache key
    scope: Mapped[str] = mapped_column(String(50))
    sumlevel: Mapped[str] = mapped_column(String(10))
    # None means 'current' TIGERweb service (most-recent vintage)
    vintage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    geoidfq: Mapped[str] = mapped_column(String(50))
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    geom: Mapped[Optional[object]] = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "scope", "sumlevel", "vintage", "geoidfq",
            name="uq_geometry_cache_row",
        ),
    )
