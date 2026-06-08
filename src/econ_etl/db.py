"""Database helpers — a thin wrapper around SQLAlchemy engines.

Defaults to a local SQLite file so the pipeline runs with zero setup, but any
SQLAlchemy URL works (e.g. ``postgresql+psycopg2://user:pass@host/db``) via the
``DATABASE_URL`` environment variable.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text


def make_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine. ``future=True`` opts into 2.0-style usage."""
    return create_engine(database_url, future=True)


def table_count(engine: Engine, table_name: str) -> int:
    """Return the number of rows in ``table_name`` (0 if it does not exist)."""
    inspector_sql = text(f"SELECT COUNT(*) FROM {table_name}")
    try:
        with engine.connect() as conn:
            return int(conn.execute(inspector_sql).scalar_one())
    except Exception:  # table missing on a fresh database
        return 0
