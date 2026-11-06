import json

import pytest

from solarcast import schemas as S
from solarcast.data import pipeline, preprocess, stages


@pytest.fixture
def stage_paths(tmp_path, monkeypatch, weather_raw, generation_raw, site):
    processed = tmp_path / "hourly.parquet"
    report = tmp_path / "validation.json"
    monkeypatch.setattr(pipeline, "PROCESSED_FILE", processed)
    monkeypatch.setattr(stages, "VALIDATION_REPORT", report)
    df = preprocess.build_site_dataset(weather_raw, generation_raw, site)
    return df, processed, report


def test_validate_stage_passes_and_writes_metrics(stage_paths):
    df, processed, report = stage_paths
    df.to_parquet(processed, index=False)
    assert stages.main(["validate"]) == 0
    r = json.loads(report.read_text())
    assert r["valid"] is True and r["rows"] == len(df) and r["null_cells"] == 0


def test_validate_stage_fails_pipeline_on_bad_data(stage_paths):
    df, processed, report = stage_paths
    df.loc[0, S.CLOUD_COVER] = 250.0
    df.to_parquet(processed, index=False)
    assert stages.main(["validate"]) == 1  # non-zero exit stops `dvc repro` before training
    r = json.loads(report.read_text())
    assert r["valid"] is False and any(S.CLOUD_COVER in f for f in r["failures"])
