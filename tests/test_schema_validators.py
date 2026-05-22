import pytest
from datetime import datetime, timezone
from pipelineguard.validators.base import (
    FieldStats, Violation, ValidationResult, ValidatorPlugin,
)
import pandas as pd
import numpy as np
from datetime import timedelta
from pipelineguard.validators.schema import (
    TypeValidator, NullableValidator, PatternValidator,
    AllowedValuesValidator, RangeValidator, RowCountValidator, FreshnessValidator,
)
from pipelineguard.contracts.models import DataContract


def _contract(fields, statistics=None, freshness=None):
    data = {
        "contract_id": "test", "version": "1.0.0", "owner": "o",
        "schema": {"fields": fields},
    }
    if statistics:
        data["statistics"] = statistics
    if freshness:
        data["freshness"] = freshness
    return DataContract.model_validate(data)


def test_violation_model():
    v = Violation(field="price", validator="range_check", severity="FAIL", message="out of range")
    assert v.field == "price"
    assert v.severity == "FAIL"
    assert v.affected_rows is None


def test_validation_result_status_fail():
    v = Violation(field="price", validator="range_check", severity="FAIL", message="bad")
    r = ValidationResult(
        run_id="r1", contract_id="c1", contract_version="1.0.0", batch_id="b1",
        timestamp=datetime.now(timezone.utc), status="FAIL",
        row_count=100, duration_ms=50.0, violations=[v],
    )
    assert r.status == "FAIL"
    assert len(r.violations) == 1


def test_field_stats_defaults():
    fs = FieldStats(
        run_id="r1", contract_id="c1", field_name="price",
        timestamp="2026-05-22T00:00:00+00:00",
        row_count=100, null_fraction=0.01,
    )
    assert fs.mean is None
    assert fs.sample_values is None
    assert fs.value_counts is None


def test_field_stats_numeric():
    fs = FieldStats(
        run_id="r1", contract_id="c1", field_name="price",
        timestamp="2026-05-22T00:00:00+00:00",
        row_count=100, null_fraction=0.0,
        mean=250.0, std=50.0,
        sample_values=[100.0, 200.0, 300.0],
    )
    assert fs.mean == pytest.approx(250.0)
    assert len(fs.sample_values) == 3


# ── TypeValidator ────────────────────────────────────────────────────────────

def test_type_validator_int_as_float_passes():
    contract = _contract([{"name": "price", "type": "float", "nullable": True}])
    df = pd.DataFrame({"price": pd.array([1, 2, 3], dtype="int64")})
    assert TypeValidator().check(df, contract) == []


def test_type_validator_object_as_float_fails():
    contract = _contract([{"name": "price", "type": "float", "nullable": True}])
    df = pd.DataFrame({"price": ["a", "b", "c"]})
    violations = TypeValidator().check(df, contract)
    assert len(violations) == 1
    assert violations[0].severity == "FAIL"
    assert violations[0].validator == "type_check"


def test_type_validator_missing_column_fails():
    contract = _contract([{"name": "price", "type": "float", "nullable": True}])
    df = pd.DataFrame({"other": [1.0]})
    violations = TypeValidator().check(df, contract)
    assert len(violations) == 1
    assert "not found" in violations[0].message


def test_type_validator_string_passes():
    contract = _contract([{"name": "name", "type": "string", "nullable": True}])
    df = pd.DataFrame({"name": ["a", "b"]})
    assert TypeValidator().check(df, contract) == []


def test_type_validator_timestamp_passes():
    contract = _contract([{"name": "ts", "type": "timestamp", "nullable": True}])
    df = pd.DataFrame({"ts": pd.to_datetime(["2026-01-01", "2026-01-02"])})
    assert TypeValidator().check(df, contract) == []


# ── NullableValidator ────────────────────────────────────────────────────────

def test_nullable_validator_no_nulls_on_nullable_passes():
    contract = _contract([{"name": "price", "type": "float", "nullable": True}])
    df = pd.DataFrame({"price": [1.0, 2.0]})
    assert NullableValidator().check(df, contract) == []


def test_nullable_validator_null_on_non_nullable_fails():
    contract = _contract([{"name": "price", "type": "float", "nullable": False}])
    df = pd.DataFrame({"price": [1.0, None]})
    violations = NullableValidator().check(df, contract)
    assert len(violations) == 1
    assert violations[0].affected_rows == 1


def test_nullable_validator_max_null_fraction_exceeded_fails():
    contract = _contract(
        [{"name": "price", "type": "float", "nullable": True}],
        statistics={"completeness": {"max_null_fraction": 0.02}},
    )
    df = pd.DataFrame({"price": [None] * 10 + [1.0] * 90})
    violations = NullableValidator().check(df, contract)
    assert len(violations) == 1
    assert violations[0].metric == pytest.approx(0.10)


def test_nullable_validator_missing_column_skipped():
    contract = _contract([{"name": "price", "type": "float", "nullable": False}])
    df = pd.DataFrame({"other": [1.0]})
    assert NullableValidator().check(df, contract) == []


# ── PatternValidator ─────────────────────────────────────────────────────────

def test_pattern_validator_all_match_passes():
    contract = _contract([{"name": "pid", "type": "string", "nullable": False, "pattern": "^[A-Z0-9]{8}$"}])
    df = pd.DataFrame({"pid": ["ABCD1234", "XY3Z9876"]})
    assert PatternValidator().check(df, contract) == []


def test_pattern_validator_mismatches_fail():
    contract = _contract([{"name": "pid", "type": "string", "nullable": False, "pattern": "^[A-Z]{4}$"}])
    df = pd.DataFrame({"pid": ["ABCD", "1234", "XY12"]})
    violations = PatternValidator().check(df, contract)
    assert len(violations) == 1
    assert violations[0].affected_rows == 2


def test_pattern_validator_no_pattern_skipped():
    contract = _contract([{"name": "name", "type": "string", "nullable": True}])
    df = pd.DataFrame({"name": ["anything"]})
    assert PatternValidator().check(df, contract) == []


# ── AllowedValuesValidator ───────────────────────────────────────────────────

def test_allowed_values_all_valid_passes():
    contract = _contract([{"name": "store", "type": "string", "nullable": False,
                           "allowed_values": ["jumia", "avito"]}])
    df = pd.DataFrame({"store": ["jumia", "avito", "jumia"]})
    assert AllowedValuesValidator().check(df, contract) == []


def test_allowed_values_unexpected_fails():
    contract = _contract([{"name": "store", "type": "string", "nullable": False,
                           "allowed_values": ["jumia", "avito"]}])
    df = pd.DataFrame({"store": ["jumia", "marjane"]})
    violations = AllowedValuesValidator().check(df, contract)
    assert len(violations) == 1
    assert violations[0].affected_rows == 1


def test_allowed_values_no_constraint_skipped():
    contract = _contract([{"name": "name", "type": "string", "nullable": True}])
    df = pd.DataFrame({"name": ["x", "y"]})
    assert AllowedValuesValidator().check(df, contract) == []


# ── RangeValidator ───────────────────────────────────────────────────────────

def test_range_validator_within_range_passes():
    contract = _contract([{"name": "price", "type": "float", "nullable": False, "min": 0.01, "max": 1000.0}])
    df = pd.DataFrame({"price": [0.01, 500.0, 1000.0]})
    assert RangeValidator().check(df, contract) == []


def test_range_validator_below_min_fails():
    contract = _contract([{"name": "price", "type": "float", "nullable": False, "min": 0.01}])
    df = pd.DataFrame({"price": [-1.0, 0.005, 100.0]})
    violations = RangeValidator().check(df, contract)
    assert len(violations) == 1
    assert violations[0].affected_rows == 2


def test_range_validator_no_range_skipped():
    contract = _contract([{"name": "price", "type": "float", "nullable": False}])
    df = pd.DataFrame({"price": [-999.0]})
    assert RangeValidator().check(df, contract) == []


# ── RowCountValidator ────────────────────────────────────────────────────────

def test_row_count_validator_sufficient_passes():
    contract = _contract(
        [{"name": "price", "type": "float", "nullable": False}],
        statistics={"completeness": {"min_row_count": 10}},
    )
    df = pd.DataFrame({"price": range(100)})
    assert RowCountValidator().check(df, contract) == []


def test_row_count_validator_insufficient_fails():
    contract = _contract(
        [{"name": "price", "type": "float", "nullable": False}],
        statistics={"completeness": {"min_row_count": 100}},
    )
    df = pd.DataFrame({"price": range(5)})
    violations = RowCountValidator().check(df, contract)
    assert len(violations) == 1
    assert violations[0].severity == "FAIL"
    assert violations[0].field is None


def test_row_count_validator_no_completeness_skipped():
    contract = _contract([{"name": "price", "type": "float", "nullable": False}])
    df = pd.DataFrame({"price": [1.0]})
    assert RowCountValidator().check(df, contract) == []


# ── FreshnessValidator ───────────────────────────────────────────────────────

def test_freshness_validator_recent_passes():
    contract = _contract(
        [{"name": "ts", "type": "timestamp", "nullable": False}],
        freshness={"max_delay_minutes": 60},
    )
    df = pd.DataFrame({"ts": [datetime.now(timezone.utc) - timedelta(minutes=30)]})
    assert FreshnessValidator().check(df, contract) == []


def test_freshness_validator_stale_warns():
    contract = _contract(
        [{"name": "ts", "type": "timestamp", "nullable": False}],
        freshness={"max_delay_minutes": 60},
    )
    df = pd.DataFrame({"ts": [datetime.now(timezone.utc) - timedelta(minutes=90)]})
    violations = FreshnessValidator().check(df, contract)
    assert len(violations) == 1
    assert violations[0].severity == "WARN"


def test_freshness_validator_no_freshness_skipped():
    contract = _contract([{"name": "ts", "type": "timestamp", "nullable": False}])
    df = pd.DataFrame({"ts": [datetime(2020, 1, 1)]})
    assert FreshnessValidator().check(df, contract) == []
