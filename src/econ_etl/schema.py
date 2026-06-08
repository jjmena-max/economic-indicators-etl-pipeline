"""Data-quality contract for the curated table, enforced with pandera.

Validation runs at the boundary between transform and load, so malformed data
fails the pipeline loudly instead of silently polluting the database.
"""

from __future__ import annotations

from pandera.pandas import Check, Column, DataFrameSchema

CURRENT_YEAR = 2100  # generous upper bound; guards against garbage dates

curated_schema = DataFrameSchema(
    {
        "country_code": Column(str, Check.str_length(min_value=2, max_value=3)),
        "country_name": Column(str, nullable=False),
        "indicator_code": Column(str, nullable=False),
        "indicator_name": Column(str, nullable=False),
        "year": Column(int, Check.in_range(1960, CURRENT_YEAR)),
        "value": Column(float, nullable=False),
        "ingested_at": Column("datetime64[ns]", nullable=False),
    },
    # A (country, indicator, year) triple must be unique after transformation.
    unique=["country_code", "indicator_code", "year"],
    strict=True,
    coerce=True,
)
