"""Tests for the transform step and its data-quality contract."""

from __future__ import annotations

import pandera.errors
import pytest

from econ_etl.transform import CURATED_COLUMNS, transform


def test_transform_shapes_and_drops_nulls(sample_raw):
    df = transform(sample_raw)
    # Three raw rows, one with a null value -> two curated rows.
    assert len(df) == 2
    assert list(df.columns) == CURATED_COLUMNS
    assert df["value"].notna().all()
    assert df["year"].dtype.kind == "i"
    assert df["value"].dtype.kind == "f"


def test_transform_is_sorted_and_deduplicated(sample_raw):
    # Duplicate the 2021 observation; transform must collapse it.
    raw = sample_raw + [sample_raw[0]]
    df = transform(raw)
    assert len(df) == 2
    assert list(df["year"]) == [2020, 2021]  # ascending


def test_transform_empty_returns_valid_empty_frame():
    df = transform([])
    assert df.empty
    assert list(df.columns) == CURATED_COLUMNS


def test_schema_rejects_bad_year(sample_raw):
    raw = [dict(sample_raw[0])]
    raw[0]["date"] = "1700"  # before the allowed 1960 lower bound
    with pytest.raises(pandera.errors.SchemaError):
        transform(raw)
