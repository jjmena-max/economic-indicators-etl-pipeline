"""Load step: write the curated DataFrame into the target SQL table.

The load is *idempotent*: re-running the pipeline replaces existing rows for the
same (country, indicator, year) keys rather than appending duplicates. For the
small volumes here we implement this with a delete-by-key + append in a single
transaction, which works identically on SQLite and Postgres.
"""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)


def load(df: pd.DataFrame, engine: Engine, table_name: str) -> int:
    """Upsert ``df`` into ``table_name``; returns the number of rows written."""
    if df.empty:
        logger.warning("Nothing to load: curated DataFrame is empty")
        return 0

    _ensure_table(engine, table_name)

    keys = (
        df[["country_code", "indicator_code", "year"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )

    with engine.begin() as conn:
        delete_sql = text(
            f"DELETE FROM {table_name} "
            "WHERE country_code = :c AND indicator_code = :i AND year = :y"
        )
        for country_code, indicator_code, year in keys:
            conn.execute(
                delete_sql, {"c": country_code, "i": indicator_code, "y": int(year)}
            )
        df.to_sql(table_name, conn, if_exists="append", index=False)

    logger.info("Loaded %s rows into %s", len(df), table_name)
    return len(df)


def _ensure_table(engine: Engine, table_name: str) -> None:
    """Create the target table with an explicit schema if it does not exist."""
    ddl = text(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            country_code   TEXT    NOT NULL,
            country_name   TEXT    NOT NULL,
            indicator_code TEXT    NOT NULL,
            indicator_name TEXT    NOT NULL,
            year           INTEGER NOT NULL,
            value          REAL    NOT NULL,
            ingested_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (country_code, indicator_code, year)
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(ddl)
