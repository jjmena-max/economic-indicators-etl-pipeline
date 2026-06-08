"""Shared pytest fixtures.

Everything here is offline: the World Bank API is faked and the database is a
throwaway SQLite file in a temp directory, so the suite runs anywhere (incl. CI)
with no network access and no credentials.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the ``src`` layout importable without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from econ_etl.config import Settings  # noqa: E402


def _observation(country_iso3: str, country_name: str, indicator: str, name: str, year: str, value):
    """Build one observation in the exact shape the World Bank API returns."""
    return {
        "indicator": {"id": indicator, "value": name},
        "country": {"id": country_iso3[:2], "value": country_name},
        "countryiso3code": country_iso3,
        "date": year,
        "value": value,
        "unit": "",
        "obs_status": "",
        "decimal": 1,
    }


@pytest.fixture
def sample_raw():
    """A small raw extract with a real-world quirk: one null value to be dropped."""
    return [
        _observation("COL", "Colombia", "FP.CPI.TOTL.ZG", "Inflation", "2021", 3.5),
        _observation("COL", "Colombia", "FP.CPI.TOTL.ZG", "Inflation", "2020", 2.5),
        _observation("COL", "Colombia", "FP.CPI.TOTL.ZG", "Inflation", "2019", None),
    ]


@pytest.fixture
def wb_page_factory():
    """Return a helper that builds a World Bank ``[meta, rows]`` page envelope."""

    def _make(rows, page=1, pages=1, total=None):
        meta = {
            "page": page,
            "pages": pages,
            "per_page": len(rows),
            "total": total if total is not None else len(rows),
        }
        return [meta, rows]

    return _make


@pytest.fixture
def settings(tmp_path):
    """Settings wired to a temp SQLite DB and a single country/indicator."""
    db_path = tmp_path / "test.db"
    return Settings(
        countries=["COL"],
        indicators={"FP.CPI.TOTL.ZG": "Inflation, consumer prices (annual %)"},
        start_year=2019,
        end_year=2021,
        database_url=f"sqlite:///{db_path.as_posix()}",
        table_name="economic_indicators",
    )
