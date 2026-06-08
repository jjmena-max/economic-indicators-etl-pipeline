"""End-to-end test of the orchestration with a faked extract step."""

from __future__ import annotations

from econ_etl import pipeline as pipeline_mod
from econ_etl.pipeline import run_pipeline


def test_run_pipeline_end_to_end(monkeypatch, settings, sample_raw):
    # Replace the network extract with our in-memory sample.
    monkeypatch.setattr(pipeline_mod, "extract", lambda _settings: sample_raw)

    result = run_pipeline(settings)

    assert result.extracted == 3   # 3 raw observations
    assert result.curated == 2     # 1 null dropped
    assert result.loaded == 2
    assert result.rows_in_table == 2


def test_run_pipeline_idempotent(monkeypatch, settings, sample_raw):
    monkeypatch.setattr(pipeline_mod, "extract", lambda _settings: sample_raw)

    run_pipeline(settings)
    second = run_pipeline(settings)

    assert second.rows_in_table == 2  # re-running does not duplicate
