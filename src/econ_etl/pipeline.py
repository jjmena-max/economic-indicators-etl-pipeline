"""Pipeline orchestration: wire extract -> transform -> load together.

This module exposes a single :func:`run_pipeline` entry point used by both the
standalone CLI (``scripts/run_pipeline.py``) and the Airflow DAG.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from .config import Settings, load_settings
from .db import make_engine, table_count
from .extract import extract
from .load import load
from .transform import transform

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    """Summary of one pipeline run, handy for logging and tests."""

    extracted: int
    curated: int
    loaded: int
    rows_in_table: int


def run_pipeline(settings: Settings | None = None) -> RunResult:
    """Run the full ETL and return a :class:`RunResult` summary."""
    settings = settings or load_settings()
    logger.info(
        "Starting ETL | countries=%s indicators=%s years=%s-%s -> %s",
        settings.countries,
        settings.indicator_codes,
        settings.start_year,
        settings.end_year,
        settings.database_url,
    )

    raw = extract(settings)
    curated: pd.DataFrame = transform(raw)

    engine = make_engine(settings.database_url)
    loaded = load(curated, engine, settings.table_name)
    rows_in_table = table_count(engine, settings.table_name)

    result = RunResult(
        extracted=len(raw),
        curated=len(curated),
        loaded=loaded,
        rows_in_table=rows_in_table,
    )
    logger.info("ETL finished | %s", result)
    return result
