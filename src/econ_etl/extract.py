"""Extract step: pull raw observations from the World Bank Open Data API.

The World Bank API needs no API key. For a given country and indicator it
returns a JSON array of two elements: ``[page_metadata, [observations]]``.
Results are paginated; we follow the ``pages`` field in the metadata.

API reference: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.worldbank.org/v2"


class ExtractError(RuntimeError):
    """Raised when the World Bank API cannot be read successfully."""


def _get_json(url: str, params: dict[str, Any], *, timeout: int, max_retries: int) -> Any:
    """GET a URL with simple exponential-backoff retries, returning parsed JSON."""
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:  # network or JSON error
            last_exc = exc
            wait = 2 ** (attempt - 1)
            logger.warning("Request failed (attempt %s/%s): %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(wait)
    raise ExtractError(f"Failed to GET {url} after {max_retries} attempts") from last_exc


def fetch_indicator(
    country: str,
    indicator: str,
    start_year: int,
    end_year: int,
    *,
    per_page: int = 1000,
    timeout: int = 30,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """Fetch every observation of one indicator for one country (all pages)."""
    url = f"{BASE_URL}/country/{country}/indicator/{indicator}"
    base_params = {
        "format": "json",
        "per_page": per_page,
        "date": f"{start_year}:{end_year}",
    }

    first = _get_json(url, {**base_params, "page": 1}, timeout=timeout, max_retries=max_retries)
    meta, rows = _unpack(first, country, indicator)
    observations: list[dict[str, Any]] = list(rows or [])

    total_pages = int(meta.get("pages", 1))
    for page in range(2, total_pages + 1):
        payload = _get_json(
            url, {**base_params, "page": page}, timeout=timeout, max_retries=max_retries
        )
        _, more = _unpack(payload, country, indicator)
        observations.extend(more or [])

    logger.info(
        "Extracted %s observations for %s / %s", len(observations), country, indicator
    )
    return observations


def _unpack(payload: Any, country: str, indicator: str) -> tuple[dict[str, Any], list[Any]]:
    """Validate the World Bank envelope and split metadata from observations."""
    if not isinstance(payload, list) or len(payload) != 2:
        # The API returns a single-element list with a 'message' on errors.
        message = payload[0] if isinstance(payload, list) and payload else payload
        raise ExtractError(
            f"Unexpected API response for {country}/{indicator}: {message!r}"
        )
    meta, rows = payload
    return meta or {}, rows or []


def extract(settings) -> list[dict[str, Any]]:
    """Extract every (country, indicator) pair declared in ``settings``."""
    raw: list[dict[str, Any]] = []
    for country in settings.countries:
        for indicator in settings.indicator_codes:
            raw.extend(
                fetch_indicator(
                    country,
                    indicator,
                    settings.start_year,
                    settings.end_year,
                    per_page=settings.per_page,
                    timeout=settings.request_timeout,
                    max_retries=settings.max_retries,
                )
            )
    return raw
