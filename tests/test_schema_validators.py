import pytest
from datetime import datetime, timezone
from pipelineguard.validators.base import (
    FieldStats, Violation, ValidationResult, ValidatorPlugin,
)


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
