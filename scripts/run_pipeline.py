#!/usr/bin/env python
"""Standalone entry point: run the ETL without an orchestrator.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --config config/indicators.yaml --export out.csv

Environment:
    DATABASE_URL   SQLAlchemy URL for the target DB (default: local SQLite file).
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

# Make ``src`` importable when run directly from a clone (no install needed).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from econ_etl.config import load_settings  # noqa: E402
from econ_etl.db import make_engine  # noqa: E402
from econ_etl.pipeline import run_pipeline  # noqa: E402
from econ_etl.snapshot import snapshot_enabled, upload_snapshot  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the economic-indicators ETL pipeline.")
    parser.add_argument("--config", help="Path to indicators.yaml", default=None)
    parser.add_argument("--database-url", help="Override the target DATABASE_URL", default=None)
    parser.add_argument("--export", help="Optional path to also export the table as CSV")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    settings = load_settings(args.config, database_url=args.database_url)
    result = run_pipeline(settings)

    print(
        f"\nDone. extracted={result.extracted} curated={result.curated} "
        f"loaded={result.loaded} rows_in_table={result.rows_in_table}"
    )

    if args.export:
        engine = make_engine(settings.database_url)
        df = pd.read_sql_table(settings.table_name, engine)
        df.to_csv(args.export, index=False)
        print(f"Exported {len(df)} rows to {args.export}")

    # In the cloud (SNAPSHOT_ACCOUNT_URL set by the Azure job), keep a
    # timestamped CSV copy of the curated table in Blob Storage for lineage.
    if snapshot_enabled():
        engine = make_engine(settings.database_url)
        df = pd.read_sql_table(settings.table_name, engine)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            df.to_csv(tmp.name, index=False)
            tmp_path = tmp.name
        try:
            url = upload_snapshot(tmp_path)
            if url:
                print(f"Snapshotted {len(df)} rows to {url}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
