"""Initial tables: census_long and geometry_cache.

Revision ID: 001
Revises:
Create Date: 2026-05-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "census_long",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("survey", sa.String(50), nullable=False),
        sa.Column("vintage", sa.Integer, nullable=False),
        sa.Column("group_code", sa.String(20), nullable=False),
        sa.Column("scope", sa.String(50), nullable=False),
        sa.Column("sumlevel", sa.String(10), nullable=False),
        sa.Column("geoidfq", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("concept", sa.String(500), nullable=True),
        sa.Column("universe", sa.String(500), nullable=True),
        sa.Column("variable_label", sa.String(500), nullable=False),
        sa.Column("variable", sa.String(30), nullable=False),
        sa.Column("estimate", sa.Float, nullable=True),
        sa.Column("moe", sa.Float, nullable=True),
        sa.Column("percent_estimate", sa.Float, nullable=True),
        sa.Column("percent_moe", sa.Float, nullable=True),
        sa.Column("total_val", sa.Float, nullable=True),
        sa.UniqueConstraint(
            "survey", "vintage", "group_code", "scope", "sumlevel", "geoidfq", "variable",
            name="uq_census_long_row",
        ),
    )
    op.create_index("ix_census_long_key", "census_long", ["survey", "vintage", "group_code", "scope", "sumlevel"])

    op.create_table(
        "geometry_cache",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("scope", sa.String(50), nullable=False),
        sa.Column("sumlevel", sa.String(10), nullable=False),
        sa.Column("vintage", sa.Integer, nullable=True),
        sa.Column("geoidfq", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("geom", Geometry("GEOMETRY", srid=4326), nullable=True),
        sa.UniqueConstraint(
            "scope", "sumlevel", "vintage", "geoidfq",
            name="uq_geometry_cache_row",
        ),
    )
    op.create_index("ix_geometry_cache_key", "geometry_cache", ["scope", "sumlevel", "vintage"])


def downgrade() -> None:
    op.drop_index("ix_geometry_cache_key", table_name="geometry_cache")
    op.drop_table("geometry_cache")
    op.drop_index("ix_census_long_key", table_name="census_long")
    op.drop_table("census_long")
