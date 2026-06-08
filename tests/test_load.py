"""Tests for the load step, focusing on idempotency."""

from __future__ import annotations

from econ_etl.db import make_engine, table_count
from econ_etl.load import load
from econ_etl.transform import transform


def test_load_writes_rows(settings, sample_raw):
    df = transform(sample_raw)
    engine = make_engine(settings.database_url)

    written = load(df, engine, settings.table_name)
    assert written == 2
    assert table_count(engine, settings.table_name) == 2


def test_load_is_idempotent(settings, sample_raw):
    df = transform(sample_raw)
    engine = make_engine(settings.database_url)

    load(df, engine, settings.table_name)
    load(df, engine, settings.table_name)  # second run must not duplicate

    assert table_count(engine, settings.table_name) == 2


def test_load_updates_existing_key(settings, sample_raw):
    engine = make_engine(settings.database_url)
    load(transform(sample_raw), engine, settings.table_name)

    # Change the 2021 value and reload; row count stays, value updates.
    bumped = [dict(r) for r in sample_raw]
    bumped[0]["value"] = 99.0
    load(transform(bumped), engine, settings.table_name)

    import pandas as pd

    out = pd.read_sql_table(settings.table_name, engine)
    assert table_count(engine, settings.table_name) == 2
    val_2021 = out.loc[out["year"] == 2021, "value"].iloc[0]
    assert val_2021 == 99.0


def test_load_empty_is_noop(settings):
    import pandas as pd

    engine = make_engine(settings.database_url)
    written = load(pd.DataFrame(), engine, settings.table_name)
    assert written == 0
