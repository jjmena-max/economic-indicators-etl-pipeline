"""Tests for the extract step — all network calls are faked."""

from __future__ import annotations

import pytest

from econ_etl import extract as extract_mod
from econ_etl.extract import ExtractError, fetch_indicator


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise extract_mod.requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


def test_fetch_indicator_single_page(monkeypatch, wb_page_factory):
    rows = [
        {
            "indicator": {"id": "FP.CPI.TOTL.ZG", "value": "Inflation"},
            "country": {"id": "CO", "value": "Colombia"},
            "countryiso3code": "COL",
            "date": "2021",
            "value": 3.5,
        }
    ]
    page = wb_page_factory(rows, page=1, pages=1)
    monkeypatch.setattr(extract_mod.requests, "get", lambda *a, **k: FakeResponse(page))

    out = fetch_indicator("COL", "FP.CPI.TOTL.ZG", 2021, 2021)
    assert len(out) == 1
    assert out[0]["value"] == 3.5


def test_fetch_indicator_follows_pagination(monkeypatch, wb_page_factory):
    page1 = wb_page_factory([{"date": "2021", "value": 1.0}], page=1, pages=2, total=2)
    page2 = wb_page_factory([{"date": "2020", "value": 2.0}], page=2, pages=2, total=2)
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return FakeResponse(page1 if params["page"] == 1 else page2)

    monkeypatch.setattr(extract_mod.requests, "get", fake_get)

    out = fetch_indicator("COL", "FP.CPI.TOTL.ZG", 2020, 2021)
    assert calls["n"] == 2
    assert {r["value"] for r in out} == {1.0, 2.0}


def test_fetch_indicator_raises_on_bad_envelope(monkeypatch):
    # World Bank returns a single-element list with a message on errors.
    bad = [{"message": [{"id": "120", "value": "Invalid indicator"}]}]
    monkeypatch.setattr(extract_mod.requests, "get", lambda *a, **k: FakeResponse(bad))

    with pytest.raises(ExtractError):
        fetch_indicator("COL", "BAD.CODE", 2021, 2021)


def test_retries_then_succeeds(monkeypatch, wb_page_factory):
    page = wb_page_factory([{"date": "2021", "value": 9.9}])
    attempts = {"n": 0}

    def flaky_get(url, params=None, timeout=None):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise extract_mod.requests.ConnectionError("boom")
        return FakeResponse(page)

    monkeypatch.setattr(extract_mod.requests, "get", flaky_get)
    monkeypatch.setattr(extract_mod.time, "sleep", lambda *_: None)  # no real backoff wait

    out = fetch_indicator("COL", "FP.CPI.TOTL.ZG", 2021, 2021, max_retries=3)
    assert attempts["n"] == 2
    assert out[0]["value"] == 9.9
