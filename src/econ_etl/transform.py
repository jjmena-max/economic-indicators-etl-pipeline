"""Transform step: turn raw API envelopes into a tidy, validated DataFrame."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .schema import curated_schema

logger = logging.getLogger(__name__)

CURATED_COLUMNS = [
    "country_code",
    "country_name",
    "indicator_code",
    "indicator_name",
    "year",
    "value",
    "ingested_at",
]


def transform(raw: list[dict[str, Any]], *, validate: bool = True) -> pd.DataFrame:
    """Flatten raw observations into the curated long-format schema.

    Steps: flatten nested fields -> drop missing values -> cast types ->
    de-duplicate -> stamp ingestion time -> validate against the pandera schema.
    """
    if not raw:
        empty = pd.DataFrame(columns=CURATED_COLUMNS)
        return curated_schema.validate(empty) if validate else empty

    records = [
        {
            "country_code": row.get("countryiso3code") or _nested(row, "country", "id"),
            "country_name": _nested(row, "country", "value"),
            "indicator_code": _nested(row, "indicator", "id"),
            "indicator_name": _nested(row, "indicator", "value"),
            "year": row.get("date"),
            "value": row.get("value"),
        }
        for row in raw
    ]
    df = pd.DataFrame.from_records(records)

    # Drop observations with no value (years a country never reported).
    before = len(df)
    df = df.dropna(subset=["value"])
    logger.info("Dropped %s rows with null value", before - len(df))

    df["year"] = df["year"].astype(int)
    df["value"] = df["value"].astype(float)

    # Guard against the same observation appearing on overlapping pages.
    df = df.drop_duplicates(subset=["country_code", "indicator_code", "year"])

    df = df.sort_values(["country_code", "indicator_code", "year"]).reset_index(drop=True)
    df["ingested_at"] = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))

    df = df[CURATED_COLUMNS]
    if validate:
        df = curated_schema.validate(df)
    logger.info("Transformed dataset has %s curated rows", len(df))
    return df


def _nested(row: dict[str, Any], outer: str, inner: str) -> Any:
    block = row.get(outer)
    return block.get(inner) if isinstance(block, dict) else None
