import pytest
from datetime import datetime, timezone
from pipelineguard.store.observations import ObservationsStore, RunSummary
from pipelineguard.validators.base import FieldStats, ValidationResult, Violation


@pytest.fixture
def store(obs_db_path):
    return ObservationsStore(db_path=obs_db_path)


def _make_result(run_id="run-1", status="PASS", violations=None):
    return ValidationResult(
        run_id=run_id,
        contract_id="test_contract",
        contract_version="1.0.0",
        batch_id="batch-1",
        timestamp=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
        status=status,
        row_count=100,
        duration_ms=123.4,
        violations=violations or [],
    )


def test_write_and_get_run(store):
    store.write_run(_make_result())
    loaded = store.get_run("run-1")
    assert loaded is not None
    assert loaded.run_id == "run-1"
    assert loaded.status == "PASS"
    assert loaded.row_count == 100


def test_get_run_with_violations(store):
    v = Violation(field="price", validator="range_check", severity="FAIL", message="bad")
    store.write_run(_make_result(violations=[v]))
    loaded = store.get_run("run-1")
    assert len(loaded.violations) == 1
    assert loaded.violations[0].field == "price"
    assert loaded.violations[0].severity == "FAIL"


def test_get_run_missing_returns_none(store):
    assert store.get_run("nonexistent") is None


def test_get_baseline_returns_none_initially(store):
    assert store.get_baseline("test_contract", "price") is None


def test_write_and_get_baseline_numeric(store):
    fs = FieldStats(
        run_id="run-1", contract_id="test_contract", field_name="price",
        timestamp="2026-05-22T12:00:00+00:00",
        row_count=100, null_fraction=0.01,
        mean=250.0, std=50.0,
        sample_values=[100.0, 200.0, 300.0],
    )
    store.write_field_stats("run-1", "test_contract", [fs])
    baseline = store.get_baseline("test_contract", "price")
    assert baseline is not None
    assert baseline.mean == pytest.approx(250.0)
    assert baseline.sample_values == [100.0, 200.0, 300.0]


def test_write_and_get_baseline_categorical(store):
    fs = FieldStats(
        run_id="run-1", contract_id="test_contract", field_name="store_id",
        timestamp="2026-05-22T12:00:00+00:00",
        row_count=100, null_fraction=0.0,
        value_counts={"jumia": 0.4, "avito": 0.6},
    )
    store.write_field_stats("run-1", "test_contract", [fs])
    baseline = store.get_baseline("test_contract", "store_id")
    assert baseline.value_counts == {"jumia": 0.4, "avito": 0.6}


def test_list_runs_empty(store):
    assert store.list_runs("test_contract") == []


def test_list_runs_most_recent_first(store):
    r1 = _make_result(run_id="run-1")
    r2 = ValidationResult(
        run_id="run-2", contract_id="test_contract", contract_version="1.0.0",
        batch_id="b2",
        timestamp=datetime(2026, 5, 22, 13, 0, 0, tzinfo=timezone.utc),
        status="WARN", row_count=100, duration_ms=50.0, violations=[],
    )
    store.write_run(r1)
    store.write_run(r2)
    runs = store.list_runs("test_contract")
    assert len(runs) == 2
    assert runs[0].run_id == "run-2"


def test_list_runs_respects_limit(store):
    for i in range(5):
        store.write_run(_make_result(run_id=f"run-{i}"))
    runs = store.list_runs("test_contract", limit=3)
    assert len(runs) == 3


def test_list_runs_unknown_contract_returns_empty(store):
    assert store.list_runs("no_such_contract") == []


def test_get_baseline_returns_most_recent(store):
    fs1 = FieldStats(
        run_id="run-1", contract_id="test_contract", field_name="price",
        timestamp="2026-05-22T10:00:00+00:00",
        row_count=100, null_fraction=0.0, mean=100.0, std=10.0,
    )
    fs2 = FieldStats(
        run_id="run-2", contract_id="test_contract", field_name="price",
        timestamp="2026-05-22T12:00:00+00:00",
        row_count=200, null_fraction=0.0, mean=200.0, std=20.0,
    )
    store.write_field_stats("run-1", "test_contract", [fs1])
    store.write_field_stats("run-2", "test_contract", [fs2])
    baseline = store.get_baseline("test_contract", "price")
    assert baseline.mean == pytest.approx(200.0)


def test_get_baseline_none_fields_round_trip(store):
    fs = FieldStats(
        run_id="run-1", contract_id="test_contract", field_name="flag",
        timestamp="2026-05-22T12:00:00+00:00",
        row_count=50, null_fraction=0.0,
    )
    store.write_field_stats("run-1", "test_contract", [fs])
    baseline = store.get_baseline("test_contract", "flag")
    assert baseline is not None
    assert baseline.sample_values is None
    assert baseline.value_counts is None
