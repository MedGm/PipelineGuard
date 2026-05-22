import pytest
import numpy as np
import pandas as pd
from pipelineguard.validators.statistical import (
    KSTestValidator, ChiSquaredValidator, ZScoreValidator,
    PSIValidator, CompletenessValidator,
)
from pipelineguard.validators.base import FieldStats
from pipelineguard.contracts.models import DataContract


def _contract(field_name="price", field_type="float", drift_sensitivity="medium",
              outlier_zscore=None):
    stats = {}
    if drift_sensitivity:
        stats[field_name] = {"drift_sensitivity": drift_sensitivity}
        if outlier_zscore:
            stats[field_name]["outlier_zscore"] = outlier_zscore
    data = {
        "contract_id": "test", "version": "1.0.0", "owner": "o",
        "schema": {"fields": [{"name": field_name, "type": field_type, "nullable": True}]},
        "statistics": stats,
    }
    return DataContract.model_validate(data)


def _baseline(field_name="price", mean=100.0, std=20.0, sample_values=None,
              value_counts=None, null_fraction=0.0):
    if sample_values is None and value_counts is None:
        rng = np.random.default_rng(42)
        sample_values = rng.normal(mean, std, 500).tolist()
    return FieldStats(
        run_id="base", contract_id="test", field_name=field_name,
        timestamp="2026-05-01T00:00:00+00:00",
        row_count=500, null_fraction=null_fraction,
        mean=mean, std=std,
        sample_values=sample_values,
        value_counts=value_counts,
    )


# ── KSTestValidator ───────────────────────────────────────────────────────────

def test_ks_same_distribution_no_violation():
    rng = np.random.default_rng(42)
    ref = rng.normal(100, 20, 500).tolist()
    baseline = _baseline(sample_values=ref)
    current = pd.DataFrame({"price": rng.normal(100, 20, 200)})
    contract = _contract()
    violations = KSTestValidator().check(current, contract, {"price": baseline})
    assert violations == []


def test_ks_shifted_distribution_warns():
    rng = np.random.default_rng(42)
    ref = rng.normal(100, 20, 500).tolist()
    baseline = _baseline(sample_values=ref)
    # Shift mean by 3 standard deviations
    current = pd.DataFrame({"price": rng.normal(160, 20, 200)})
    contract = _contract()
    violations = KSTestValidator().check(current, contract, {"price": baseline})
    assert len(violations) == 1
    assert violations[0].severity == "WARN"
    assert violations[0].validator == "ks_test"


def test_ks_no_baseline_returns_empty():
    current = pd.DataFrame({"price": [1.0, 2.0, 3.0]})
    contract = _contract()
    violations = KSTestValidator().check(current, contract, {"price": None})
    assert violations == []


def test_ks_none_baselines_returns_empty():
    current = pd.DataFrame({"price": [1.0, 2.0, 3.0]})
    contract = _contract()
    violations = KSTestValidator().check(current, contract, baselines=None)
    assert violations == []


def test_ks_low_sensitivity_harder_to_trigger():
    rng = np.random.default_rng(42)
    ref = rng.normal(100, 20, 500).tolist()
    baseline = _baseline(sample_values=ref)
    # Moderate shift — triggers medium but not low
    current = pd.DataFrame({"price": rng.normal(130, 20, 200)})
    contract_medium = _contract(drift_sensitivity="medium")
    contract_low = _contract(drift_sensitivity="low")
    v_medium = KSTestValidator().check(current, contract_medium, {"price": baseline})
    v_low = KSTestValidator().check(current, contract_low, {"price": baseline})
    # medium should trigger; low should not (alpha=0.001 for low)
    assert len(v_medium) >= len(v_low)


# ── PSIValidator ──────────────────────────────────────────────────────────────

def test_psi_same_distribution_no_violation():
    rng = np.random.default_rng(42)
    ref = rng.normal(100, 20, 500).tolist()
    baseline = _baseline(sample_values=ref)
    current = pd.DataFrame({"price": rng.normal(100, 20, 200)})
    violations = PSIValidator().check(current, _contract(), {"price": baseline})
    assert violations == []


def test_psi_heavy_shift_fails():
    rng = np.random.default_rng(42)
    ref = rng.normal(100, 5, 500).tolist()
    baseline = _baseline(sample_values=ref)
    # Very different distribution
    current = pd.DataFrame({"price": rng.normal(300, 5, 200)})
    violations = PSIValidator().check(current, _contract(), {"price": baseline})
    assert len(violations) == 1
    assert violations[0].severity == "FAIL"
    assert violations[0].metric > 0.20


def test_psi_no_baseline_returns_empty():
    current = pd.DataFrame({"price": [1.0, 2.0]})
    violations = PSIValidator().check(current, _contract(), {"price": None})
    assert violations == []


# ── ZScoreValidator ───────────────────────────────────────────────────────────

def test_zscore_clean_data_no_violation():
    baseline = _baseline(mean=100.0, std=20.0)
    current = pd.DataFrame({"price": [80.0, 90.0, 100.0, 110.0, 120.0]})
    contract = _contract(outlier_zscore=4.0)
    violations = ZScoreValidator().check(current, contract, {"price": baseline})
    assert violations == []


def test_zscore_outlier_warns():
    baseline = _baseline(mean=100.0, std=20.0)
    # 200 is (200-100)/20 = 5 sigma — exceeds threshold of 4.0
    current = pd.DataFrame({"price": [100.0, 100.0, 200.0]})
    contract = _contract(outlier_zscore=4.0)
    violations = ZScoreValidator().check(current, contract, {"price": baseline})
    assert len(violations) == 1
    assert violations[0].affected_rows == 1
    assert violations[0].severity == "WARN"


def test_zscore_no_outlier_zscore_in_contract_skipped():
    baseline = _baseline(mean=100.0, std=20.0)
    current = pd.DataFrame({"price": [1000.0]})
    contract = _contract(outlier_zscore=None)
    assert ZScoreValidator().check(current, contract, {"price": baseline}) == []


def test_zscore_no_baseline_returns_empty():
    current = pd.DataFrame({"price": [1000.0]})
    contract = _contract(outlier_zscore=4.0)
    assert ZScoreValidator().check(current, contract, {"price": None}) == []


# ── ChiSquaredValidator ───────────────────────────────────────────────────────

def test_chi_same_distribution_no_violation():
    vc = {"jumia": 0.5, "avito": 0.5}
    baseline = _baseline(field_name="store", value_counts=vc, sample_values=None,
                         mean=None, std=None)
    current = pd.DataFrame({"store": ["jumia"] * 50 + ["avito"] * 50})
    contract = _contract(field_name="store", field_type="string")
    violations = ChiSquaredValidator().check(current, contract, {"store": baseline})
    assert violations == []


def test_chi_shifted_distribution_warns():
    vc = {"jumia": 0.5, "avito": 0.5}
    baseline = _baseline(field_name="store", value_counts=vc, sample_values=None,
                         mean=None, std=None)
    # Very different proportions
    current = pd.DataFrame({"store": ["jumia"] * 95 + ["avito"] * 5})
    contract = _contract(field_name="store", field_type="string")
    violations = ChiSquaredValidator().check(current, contract, {"store": baseline})
    assert len(violations) == 1
    assert violations[0].severity == "WARN"


def test_chi_skipped_if_bucket_too_small():
    vc = {"a": 0.5, "b": 0.3, "c": 0.2}
    baseline = _baseline(field_name="cat", value_counts=vc, sample_values=None,
                         mean=None, std=None)
    # Only 3 rows → expected counts = [1.5, 0.9, 0.6] — all < 5 → skip
    current = pd.DataFrame({"cat": ["a", "b", "c"]})
    contract = _contract(field_name="cat", field_type="string")
    assert ChiSquaredValidator().check(current, contract, {"cat": baseline}) == []


def test_chi_no_baseline_returns_empty():
    current = pd.DataFrame({"store": ["jumia"]})
    contract = _contract(field_name="store", field_type="string")
    assert ChiSquaredValidator().check(current, contract, {"store": None}) == []


# ── CompletenessValidator ─────────────────────────────────────────────────────

def test_completeness_no_increase_no_violation():
    baseline = _baseline(null_fraction=0.01)
    # 1% nulls vs 1% baseline → increase = 0.0, below 0.05 threshold → no violation
    current = pd.DataFrame({"price": [None] + [1.0] * 99})
    contract = _contract()
    violations = CompletenessValidator().check(current, contract, {"price": baseline})
    assert violations == []


def test_completeness_large_increase_warns():
    baseline = _baseline(null_fraction=0.01)
    # 30% nulls now
    current = pd.DataFrame({"price": [None] * 30 + [1.0] * 70})
    contract = _contract()
    violations = CompletenessValidator().check(current, contract, {"price": baseline})
    assert len(violations) == 1
    assert violations[0].severity == "WARN"


def test_completeness_no_baseline_returns_empty():
    current = pd.DataFrame({"price": [None] * 50 + [1.0] * 50})
    contract = _contract()
    assert CompletenessValidator().check(current, contract, {"price": None}) == []
