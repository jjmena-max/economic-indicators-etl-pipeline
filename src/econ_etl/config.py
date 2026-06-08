"""Configuration loading for the ETL pipeline.

Settings come from two places:
  1. A YAML file describing *what* to ingest (countries, indicators, year range).
  2. Environment variables describing *where* to load it (DATABASE_URL) and
     runtime knobs. Environment variables always win over file defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

# Repo root = three levels up from this file (src/econ_etl/config.py).
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "indicators.yaml"
DEFAULT_DB_URL = f"sqlite:///{(ROOT / 'economic_indicators.db').as_posix()}"


@dataclass(frozen=True)
class Settings:
    """Resolved pipeline settings."""

    countries: list[str]
    indicators: dict[str, str]  # World Bank code -> human readable name
    start_year: int
    end_year: int
    database_url: str
    table_name: str = "economic_indicators"
    request_timeout: int = 30
    max_retries: int = 3
    per_page: int = 1000

    @property
    def indicator_codes(self) -> list[str]:
        return list(self.indicators.keys())


def load_settings(
    config_path: str | os.PathLike[str] | None = None,
    *,
    database_url: str | None = None,
) -> Settings:
    """Build a :class:`Settings` object from a YAML file + environment overrides."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    resolved_db = (
        database_url
        or os.environ.get("DATABASE_URL")
        or raw.get("database_url")
        or DEFAULT_DB_URL
    )

    return Settings(
        countries=[c.upper() for c in raw.get("countries", ["COL"])],
        indicators=dict(raw.get("indicators", {})),
        start_year=int(raw.get("start_year", 2000)),
        end_year=int(raw.get("end_year", 2023)),
        database_url=resolved_db,
        table_name=raw.get("table_name", "economic_indicators"),
        request_timeout=int(os.environ.get("ETL_REQUEST_TIMEOUT", raw.get("request_timeout", 30))),
        max_retries=int(os.environ.get("ETL_MAX_RETRIES", raw.get("max_retries", 3))),
        per_page=int(raw.get("per_page", 1000)),
    )
