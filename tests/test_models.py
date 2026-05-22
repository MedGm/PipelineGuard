import pytest
import yaml
from pydantic import ValidationError
from pipelineguard.contracts.models import (
    DataContract, FieldSpec, ContractSummary, ContractDiff, BreakingChange,
)

VALID_YAML = """\
contract_id: test_contract
version: 1.0.0
owner: test-owner
description: A test contract
schema:
  fields:
    - name: price
      type: float
      nullable: false
      min: 0.01
      max: 1000.0
    - name: category
      type: string
      nullable: true
      allowed_values: [a, b, c]
freshness:
  max_delay_minutes: 60
remediation:
  on_schema_violation: quarantine
  alert_channels: [slack_webhook]
"""

def load(yaml_str: str) -> DataContract:
    return DataContract.model_validate(yaml.safe_load(yaml_str))

def test_valid_contract_loads():
    c = load(VALID_YAML)
    assert c.contract_id == "test_contract"
    assert c.version == "1.0.0"
    assert c.owner == "test-owner"

def test_schema_alias_populates_schema_spec():
    c = load(VALID_YAML)
    assert len(c.schema_spec.fields) == 2
    assert c.schema_spec.fields[0].name == "price"

def test_invalid_semver_two_parts_raises():
    data = yaml.safe_load(VALID_YAML)
    data["version"] = "1.0"
    with pytest.raises(ValidationError, match="MAJOR.MINOR.PATCH"):
        DataContract.model_validate(data)

def test_invalid_semver_v_prefix_raises():
    data = yaml.safe_load(VALID_YAML)
    data["version"] = "v1.0.0"
    with pytest.raises(ValidationError):
        DataContract.model_validate(data)

def test_missing_contract_id_raises():
    data = yaml.safe_load(VALID_YAML)
    del data["contract_id"]
    with pytest.raises(ValidationError):
        DataContract.model_validate(data)

def test_missing_schema_raises():
    data = yaml.safe_load(VALID_YAML)
    del data["schema"]
    with pytest.raises(ValidationError):
        DataContract.model_validate(data)

def test_field_spec_float_range():
    f = FieldSpec(name="price", type="float", nullable=False, min=0.01, max=1000.0)
    assert f.min == pytest.approx(0.01)
    assert f.max == pytest.approx(1000.0)

def test_remediation_defaults_when_absent():
    data = yaml.safe_load(VALID_YAML)
    del data["remediation"]
    c = DataContract.model_validate(data)
    assert c.remediation.on_schema_violation == "alert"
    assert c.remediation.on_drift_violation == "alert_and_continue"
    assert c.remediation.suppression_window_minutes == 30
    assert c.remediation.alert_channels == []

def test_statistics_accepts_arbitrary_keys():
    data = yaml.safe_load(VALID_YAML)
    data["statistics"] = {
        "price": {"drift_sensitivity": "high"},
        "completeness": {"min_row_count": 100, "max_null_fraction": 0.02},
    }
    c = DataContract.model_validate(data)
    assert c.statistics["price"]["drift_sensitivity"] == "high"
    assert c.statistics["completeness"]["min_row_count"] == 100

def test_contract_summary_model():
    s = ContractSummary(
        contract_id="x", version="1.0.0", owner="o", description="d"
    )
    assert s.contract_id == "x"

def test_breaking_change_model():
    bc = BreakingChange(field_name="price", change_type="removed", detail="field removed")
    assert bc.change_type == "removed"


def test_semver_leading_zeros_raises():
    data = yaml.safe_load(VALID_YAML)
    data["version"] = "01.0.0"
    with pytest.raises(ValidationError):
        DataContract.model_validate(data)


def test_extra_field_in_contract_raises():
    data = yaml.safe_load(VALID_YAML)
    data["nonexistent_field"] = "oops"
    with pytest.raises(ValidationError):
        DataContract.model_validate(data)


def test_extra_field_in_field_spec_raises():
    data = yaml.safe_load(VALID_YAML)
    data["schema"]["fields"][0]["typo_field"] = "oops"
    with pytest.raises(ValidationError):
        DataContract.model_validate(data)


def test_breaking_change_uses_field_name():
    bc = BreakingChange(field_name="price", change_type="removed", detail="field removed")
    assert bc.field_name == "price"

def test_contract_diff_model():
    diff = ContractDiff(
        contract_id="x",
        from_version="1.0.0",
        to_version="2.0.0",
        breaking_changes=[],
        minor_changes=["field 'store' added"],
    )
    assert diff.minor_changes[0] == "field 'store' added"


def test_extra_field_in_freshness_raises():
    data = yaml.safe_load(VALID_YAML)
    data["freshness"]["typo_key"] = "oops"
    with pytest.raises(ValidationError):
        DataContract.model_validate(data)
