from solarcast import config, schemas


def test_contract_columns_unique():
    assert len(schemas.PROCESSED_COLUMNS) == len(set(schemas.PROCESSED_COLUMNS))


def test_params_load():
    p = config.params()
    assert p["window"]["history_hours"] == 168
    assert p["window"]["horizon_hours"] == 24


def test_sites_load():
    assert config.sites(), "configs/sites.yaml must define at least one site"
