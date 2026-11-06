import pytest

from solarcast import schemas as S
from solarcast.data import preprocess, validate

try:
    from pandera.errors import SchemaErrors
except ImportError:  # pragma: no cover
    SchemaErrors = Exception


@pytest.fixture
def processed(weather_raw, generation_raw, site):
    return preprocess.build_site_dataset(weather_raw, generation_raw, site)


def test_valid_dataset_passes(processed):
    validate.validate_processed(processed)


def test_missing_column_fails(processed):
    with pytest.raises(SchemaErrors):
        validate.validate_processed(processed.drop(columns=[S.TEMP]))


def test_out_of_range_fails_and_summary_names_column(processed):
    bad = processed.copy()
    bad.loc[3, S.CLOUD_COVER] = 150.0
    with pytest.raises(SchemaErrors) as exc:
        validate.validate_processed(bad)
    assert S.CLOUD_COVER in validate.failure_summary(exc.value)


def test_night_rule_enforced(processed):
    bad = processed.copy()
    night_idx = bad.index[bad[S.GHI] == 0][0]
    bad.loc[night_idx, S.GENERATION_KWH] = 1.0
    with pytest.raises(SchemaErrors):
        validate.validate_processed(bad)


def test_simulated_flag_consistent_with_source(processed):
    bad = processed.copy()
    bad[S.IS_SIMULATED] = False  # pvgis rows must be simulated
    with pytest.raises(SchemaErrors):
        validate.validate_processed(bad)


def test_weather_input_row_count(weather_raw):
    w = preprocess.clean_weather(weather_raw).head(24)
    validate.validate_weather_input(w, expected_rows=24)
    with pytest.raises(ValueError):
        validate.validate_weather_input(w.head(23), expected_rows=24)
