import pytest
import warnings
from pathlib import Path
from pipelineguard.contracts.registry import ContractRegistry
from pipelineguard.exceptions import ContractNotFound, ContractVersionExists

V1_YAML = """\
contract_id: product_price
version: 1.0.0
owner: test-owner
description: v1
schema:
  fields:
    - name: price
      type: float
      nullable: false
"""

V2_YAML = """\
contract_id: product_price
version: 2.0.0
owner: test-owner
description: v2 - added currency
schema:
  fields:
    - name: price
      type: float
      nullable: false
    - name: currency
      type: string
      nullable: false
"""

V1_PATCH_YAML = """\
contract_id: product_price
version: 1.0.1
owner: test-owner
description: v1 patch - added store
schema:
  fields:
    - name: price
      type: float
      nullable: false
    - name: store
      type: string
      nullable: true
"""

V2_BREAKING_YAML = """\
contract_id: product_price
version: 2.0.0
owner: test-owner
description: v2 - type change on price
schema:
  fields:
    - name: price
      type: string
      nullable: false
"""


def write(tmp_path: Path, name: str, content: str) -> str:
    p = tmp_path / name
    p.write_text(content)
    return str(p)


@pytest.fixture
def registry(db_path: str) -> ContractRegistry:
    return ContractRegistry(db_path=db_path)


def test_register_and_load(registry, tmp_path):
    path = write(tmp_path, "v1.yaml", V1_YAML)
    contract = registry.register(path)
    assert contract.contract_id == "product_price"
    assert contract.version == "1.0.0"

    loaded = registry.load("product_price")
    assert loaded.version == "1.0.0"
    assert loaded.schema_spec.fields[0].name == "price"


def test_loaded_contract_matches_registered(registry, tmp_path):
    path = write(tmp_path, "v1.yaml", V1_YAML)
    registered = registry.register(path)
    loaded = registry.load("product_price", version="1.0.0")
    assert loaded.contract_id == registered.contract_id
    assert loaded.version == registered.version
    assert len(loaded.schema_spec.fields) == len(registered.schema_spec.fields)


def test_register_duplicate_version_raises(registry, tmp_path):
    path = write(tmp_path, "v1.yaml", V1_YAML)
    registry.register(path)
    with pytest.raises(ContractVersionExists):
        registry.register(path)


def test_load_missing_contract_raises(registry):
    with pytest.raises(ContractNotFound):
        registry.load("nonexistent")


def test_load_specific_version(registry, tmp_path):
    write_v1 = write(tmp_path, "v1.yaml", V1_YAML)
    write_v2 = write(tmp_path, "v2.yaml", V2_YAML)
    registry.register(write_v1)
    registry.register(write_v2)
    loaded = registry.load("product_price", version="1.0.0")
    assert loaded.version == "1.0.0"


def test_load_no_version_returns_semver_latest(registry, tmp_path):
    # Register patch first, then base — latest must still be 1.0.1
    # Registering 1.0.0 after 1.0.1 triggers an expected semver bump warning
    # (1.0.1 -> 1.0.0 removes the 'store' field). Suppress it.
    write_patch = write(tmp_path, "patch.yaml", V1_PATCH_YAML)
    write_v1 = write(tmp_path, "v1.yaml", V1_YAML)
    registry.register(write_patch)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        registry.register(write_v1)
    latest = registry.load("product_price")
    assert latest.version == "1.0.1"


def test_list_returns_all_versions(registry, tmp_path):
    registry.register(write(tmp_path, "v1.yaml", V1_YAML))
    registry.register(write(tmp_path, "v2.yaml", V2_YAML))
    summaries = registry.list()
    assert len(summaries) == 2
    versions = {s.version for s in summaries}
    assert versions == {"1.0.0", "2.0.0"}


def test_list_returns_contract_summary_fields(registry, tmp_path):
    registry.register(write(tmp_path, "v1.yaml", V1_YAML))
    summaries = registry.list()
    assert summaries[0].contract_id == "product_price"
    assert summaries[0].owner == "test-owner"


def test_diff_detects_added_field(registry, tmp_path):
    registry.register(write(tmp_path, "v1.yaml", V1_YAML))
    registry.register(write(tmp_path, "v2.yaml", V2_YAML))
    diff = registry.diff("product_price", "1.0.0", "2.0.0")
    assert diff.contract_id == "product_price"
    assert diff.breaking_changes == []
    assert any("currency" in c for c in diff.minor_changes)


def test_diff_detects_breaking_type_change(registry, tmp_path):
    registry.register(write(tmp_path, "v1.yaml", V1_YAML))
    registry.register(write(tmp_path, "v2b.yaml", V2_BREAKING_YAML))
    diff = registry.diff("product_price", "1.0.0", "2.0.0")
    assert len(diff.breaking_changes) == 1
    assert diff.breaking_changes[0].change_type == "type_changed"
    assert diff.breaking_changes[0].field_name == "price"


def test_register_warns_on_invalid_semver_bump(registry, tmp_path):
    registry.register(write(tmp_path, "v1.yaml", V1_YAML))
    # breaking change (type change) but only minor bump — should warn
    minor_breaking = V2_BREAKING_YAML.replace("version: 2.0.0", "version: 1.1.0")
    path = write(tmp_path, "v1_1_breaking.yaml", minor_breaking)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        registry.register(path)
    assert any("major" in str(w.message).lower() for w in caught)
