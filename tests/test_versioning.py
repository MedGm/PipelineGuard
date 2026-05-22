import pytest
import yaml
from pipelineguard.contracts.models import DataContract
from pipelineguard.contracts.versioning import (
    parse_version, latest_version, classify_diff, validate_bump,
)

def make_contract(version: str, fields: list | None = None) -> DataContract:
    if fields is None:
        fields = [{"name": "price", "type": "float", "nullable": False}]
    data = {
        "contract_id": "test",
        "version": version,
        "owner": "owner",
        "description": "",
        "schema": {"fields": fields},
    }
    return DataContract.model_validate(data)


def test_parse_version_basic():
    assert parse_version("1.2.3") == (1, 2, 3)

def test_parse_version_double_digits():
    assert parse_version("10.20.30") == (10, 20, 30)

def test_latest_version_picks_semver_max():
    assert latest_version(["1.0.0", "2.0.0", "1.9.0"]) == "2.0.0"

def test_latest_version_not_lexicographic():
    # Lexicographic sort would wrongly put "9.0.0" > "10.0.0"
    assert latest_version(["9.0.0", "10.0.0"]) == "10.0.0"

def test_classify_diff_removed_field_is_breaking():
    old = make_contract("1.0.0")
    new = make_contract("2.0.0", fields=[])
    diff = classify_diff(old, new)
    assert len(diff.breaking_changes) == 1
    assert diff.breaking_changes[0].change_type == "removed"
    assert diff.breaking_changes[0].field_name == "price"

def test_classify_diff_type_change_is_breaking():
    old = make_contract("1.0.0")
    new = make_contract("2.0.0", fields=[{"name": "price", "type": "string", "nullable": False}])
    diff = classify_diff(old, new)
    assert len(diff.breaking_changes) == 1
    assert diff.breaking_changes[0].change_type == "type_changed"

def test_classify_diff_added_field_is_minor():
    old = make_contract("1.0.0")
    new = make_contract("1.0.1", fields=[
        {"name": "price", "type": "float", "nullable": False},
        {"name": "store", "type": "string", "nullable": True},
    ])
    diff = classify_diff(old, new)
    assert len(diff.breaking_changes) == 0
    assert len(diff.minor_changes) == 1
    assert "store" in diff.minor_changes[0]

def test_classify_diff_no_changes():
    old = make_contract("1.0.0")
    new = make_contract("1.0.1")  # same fields, patch bump
    diff = classify_diff(old, new)
    assert diff.breaking_changes == []
    assert diff.minor_changes == []

def test_validate_bump_warns_breaking_without_major():
    old = make_contract("1.0.0")
    new = make_contract("1.1.0", fields=[])  # removed field, but only minor bump
    diff = classify_diff(old, new)
    warning = validate_bump("1.0.0", "1.1.0", diff)
    assert warning is not None
    assert "major" in warning.lower()

def test_validate_bump_ok_on_correct_major_bump():
    old = make_contract("1.0.0")
    new = make_contract("2.0.0", fields=[])
    diff = classify_diff(old, new)
    assert validate_bump("1.0.0", "2.0.0", diff) is None

def test_validate_bump_ok_no_changes():
    old = make_contract("1.0.0")
    new = make_contract("1.0.1")
    diff = classify_diff(old, new)
    assert validate_bump("1.0.0", "1.0.1", diff) is None
