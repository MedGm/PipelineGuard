import pytest
import pandas as pd
import numpy as np
from pipelineguard.validators.engine import Validator
from pipelineguard.store.observations import ObservationsStore
from pipelineguard.contracts.models import DataContract


def _contract():
    return DataContract.model_validate({
        "contract_id": "price_contract",
        "version": "1.0.0",
        "owner": "test",
        "schema": {"fields": [
            {"name": "price", "type": "float", "nullable": False, "min": 0.01, "max": 10000.0},
            {"name": "store", "type": "string", "nullable": False,
             "allowed_values": ["jumia", "avito"]},
        ]},
        "statistics": {
            "price": {"drift_sensitivity": "medium", "outlier_zscore": 4.0},
            "store": {"drift_sensitivity": "medium"},
        },
    })


def _good_df(n=100):
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "price": rng.uniform(1.0, 9000.0, n),
        "store": rng.choice(["jumia", "avito"], n).tolist(),
    })


def _bad_df():
    return pd.DataFrame({
        "price": [-1.0, -2.0, 9999.0],
        "store": ["jumia", "jumia", "jumia"],
    })


def test_validate_clean_df_returns_pass(obs_db_path):
    v = Validator(_contract(), obs_db_path=obs_db_path)
    result = v.validate(_good_df())
    assert result.status == "PASS"
    assert result.violations == []
    assert result.row_count == 100


def test_validate_bad_df_returns_fail(obs_db_path):
    v = Validator(_contract(), obs_db_path=obs_db_path)
    result = v.validate(_bad_df())
    assert result.status == "FAIL"
    assert any(viol.severity == "FAIL" for viol in result.violations)


def test_validate_persists_run_to_store(obs_db_path):
    store = ObservationsStore(db_path=obs_db_path)
    v = Validator(_contract(), obs_store=store)
    result = v.validate(_good_df())
    loaded = store.get_run(result.run_id)
    assert loaded is not None
    assert loaded.run_id == result.run_id
    assert loaded.status == result.status


def test_validate_run_id_unique(obs_db_path):
    v = Validator(_contract(), obs_db_path=obs_db_path)
    r1 = v.validate(_good_df())
    r2 = v.validate(_good_df())
    assert r1.run_id != r2.run_id


def test_validate_duration_ms_positive(obs_db_path):
    v = Validator(_contract(), obs_db_path=obs_db_path)
    result = v.validate(_good_df())
    assert result.duration_ms > 0


def test_validate_status_fail_beats_warn(obs_db_path):
    v = Validator(_contract(), obs_db_path=obs_db_path)
    result = v.validate(_bad_df())
    assert result.status == "FAIL"


def test_validate_custom_batch_id(obs_db_path):
    v = Validator(_contract(), obs_db_path=obs_db_path)
    result = v.validate(_good_df(), batch_id="my-batch-001")
    assert result.batch_id == "my-batch-001"


def test_validate_second_run_uses_baseline(obs_db_path):
    v = Validator(_contract(), obs_db_path=obs_db_path)
    # First run bootstraps baseline
    v.validate(_good_df())
    # Second run has statistical validators active
    r2 = v.validate(_good_df())
    # No crash, result is valid
    assert r2.run_id is not None
    assert r2.status in ("PASS", "WARN", "FAIL")


def test_validate_row_count_matches_df(obs_db_path):
    v = Validator(_contract(), obs_db_path=obs_db_path)
    df = _good_df(n=50)
    result = v.validate(df)
    assert result.row_count == 50
