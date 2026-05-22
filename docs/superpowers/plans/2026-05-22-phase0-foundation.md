# PipelineGuard Phase 0 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the contract schema, Pydantic v2 models, SQLite-backed registry, CLI scaffold, and test suite — milestone: `pg contract register contracts/ecommerce_price.yaml` succeeds and full test suite passes.

**Architecture:** `src/` layout Python package. Pydantic v2 models parse YAML contracts. SQLite stores contracts via raw `sqlite3` (no ORM). Typer CLI wraps the registry. TDD throughout — write failing test, implement minimum code, verify pass, commit.

**Tech Stack:** Python 3.11+, Pydantic v2, PyYAML, Typer, sqlite3 (stdlib), pytest

---

## File Map

| File | Responsibility |
|---|---|
| `pyproject.toml` | Build config, dependencies, `pg` entry point |
| `src/pipelineguard/__init__.py` | Public API exports |
| `src/pipelineguard/exceptions.py` | All custom exceptions |
| `src/pipelineguard/_db.py` | sqlite3 connection + schema init |
| `src/pipelineguard/contracts/__init__.py` | Empty namespace |
| `src/pipelineguard/contracts/models.py` | Pydantic v2 DataContract + supporting models |
| `src/pipelineguard/contracts/versioning.py` | Semver parse, latest-version sort, diff classify, bump validate |
| `src/pipelineguard/contracts/registry.py` | ContractRegistry (register, load, list, diff) |
| `src/pipelineguard/cli/__init__.py` | Empty namespace |
| `src/pipelineguard/cli/main.py` | Typer app — `pg contract` commands + phase stubs |
| `tests/conftest.py` | `db_path` and `sample_contract_yaml` fixtures |
| `tests/test_models.py` | Unit tests for Pydantic models |
| `tests/test_versioning.py` | Unit tests for versioning logic |
| `tests/test_registry.py` | Integration tests for ContractRegistry |
| `tests/test_cli.py` | CLI tests via typer.testing.CliRunner |
| `contracts/ecommerce_price.yaml` | Example contract (milestone verification) |

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/pipelineguard/__init__.py`
- Create: `src/pipelineguard/exceptions.py`
- Create: `src/pipelineguard/_db.py`
- Create: `src/pipelineguard/contracts/__init__.py`
- Create: `src/pipelineguard/cli/__init__.py`
- Create: `tests/conftest.py`
- Create: `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p src/pipelineguard/contracts
mkdir -p src/pipelineguard/cli
mkdir -p tests
mkdir -p contracts
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pipelineguard"
version = "0.1.0"
description = "Lightweight, local-first ML pipeline data contract enforcement engine"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "typer>=0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[project.scripts]
pg = "pipelineguard.cli.main:app"

[tool.hatch.build.targets.wheel]
packages = ["src/pipelineguard"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `src/pipelineguard/exceptions.py`**

```python
class PipelineGuardError(Exception):
    pass

class ContractNotFound(PipelineGuardError):
    pass

class ContractVersionExists(PipelineGuardError):
    pass

class InvalidSemverBump(PipelineGuardError):
    pass
```

- [ ] **Step 4: Write `src/pipelineguard/_db.py`**

```python
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    contract_id   TEXT NOT NULL,
    version       TEXT NOT NULL,
    owner         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    yaml_content  TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    PRIMARY KEY (contract_id, version)
);
"""

def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
```

- [ ] **Step 5: Write empty namespace files**

`src/pipelineguard/__init__.py` — leave empty for now (filled in Task 6 after all modules exist):
```python
```

`src/pipelineguard/contracts/__init__.py`:
```python
```

`src/pipelineguard/cli/__init__.py`:
```python
```

- [ ] **Step 6: Write `tests/conftest.py`**

```python
import pytest

@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")

@pytest.fixture
def sample_contract_yaml(tmp_path) -> str:
    content = """\
contract_id: product_price_v2
version: 2.0.0
owner: el-gorrim-mohamed
description: Scraped product prices from Moroccan e-commerce stores
schema:
  fields:
    - name: product_id
      type: string
      nullable: false
      pattern: '^[A-Z0-9]{8,16}$'
    - name: price_mad
      type: float
      nullable: false
      min: 0.01
      max: 500000.0
    - name: store_id
      type: string
      nullable: false
      allowed_values: [jumia, hmizate, avito, marjane]
    - name: scraped_at
      type: timestamp
      nullable: false
statistics:
  price_mad:
    expected_distribution: lognormal
    drift_sensitivity: medium
    outlier_zscore: 4.0
  completeness:
    min_row_count: 100
    max_null_fraction: 0.02
freshness:
  max_delay_minutes: 60
remediation:
  on_schema_violation: quarantine
  on_drift_violation: alert_and_continue
  on_freshness_violation: alert
  alert_channels: [slack_webhook, email]
  suppression_window_minutes: 30
"""
    p = tmp_path / "product_price_v2.yaml"
    p.write_text(content)
    return str(p)
```

- [ ] **Step 7: Write `.gitignore`**

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
.venv/
*.db
*.duckdb
```

- [ ] **Step 8: Install in editable mode and verify**

```bash
pip install -e ".[dev]"
```

Expected: installs without error. `pg --help` will fail (cli/main.py not yet written) but the package imports.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml src/ tests/conftest.py contracts/ .gitignore
git commit -m "chore: project scaffold — src layout, exceptions, db init, conftest"
```

---

## Task 2: Pydantic v2 Contract Models

**Files:**
- Create: `tests/test_models.py`
- Create: `src/pipelineguard/contracts/models.py`

- [ ] **Step 1: Write failing tests**

`tests/test_models.py`:
```python
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
    bc = BreakingChange(field="price", change_type="removed", detail="field removed")
    assert bc.change_type == "removed"

def test_contract_diff_model():
    diff = ContractDiff(
        contract_id="x",
        from_version="1.0.0",
        to_version="2.0.0",
        breaking_changes=[],
        minor_changes=["field 'store' added"],
    )
    assert diff.minor_changes[0] == "field 'store' added"
```

- [ ] **Step 2: Run tests — verify they fail with ImportError**

```bash
pytest tests/test_models.py -v
```

Expected: `ImportError: cannot import name 'DataContract' from 'pipelineguard.contracts.models'`

- [ ] **Step 3: Write `src/pipelineguard/contracts/models.py`**

```python
from __future__ import annotations
import re
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class FieldSpec(BaseModel):
    name: str
    type: Literal["string", "integer", "float", "boolean", "timestamp"]
    nullable: bool = True
    pattern: Optional[str] = None
    allowed_values: Optional[list[str]] = None
    min: Optional[float] = None
    max: Optional[float] = None


class SchemaSpec(BaseModel):
    fields: list[FieldSpec]


class FreshnessSpec(BaseModel):
    max_delay_minutes: int


class RemediationSpec(BaseModel):
    on_schema_violation: Literal[
        "quarantine", "alert", "soft_block", "alert_and_continue"
    ] = "alert"
    on_drift_violation: Literal[
        "quarantine", "alert", "soft_block", "alert_and_continue"
    ] = "alert_and_continue"
    on_freshness_violation: Literal[
        "quarantine", "alert", "soft_block", "alert_and_continue"
    ] = "alert"
    alert_channels: list[str] = Field(default_factory=list)
    suppression_window_minutes: int = 30


class DataContract(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    contract_id: str
    version: str
    owner: str
    description: str = ""
    schema_spec: SchemaSpec = Field(alias="schema")
    statistics: dict[str, Any] = Field(default_factory=dict)
    freshness: Optional[FreshnessSpec] = None
    remediation: RemediationSpec = Field(default_factory=RemediationSpec)

    @field_validator("version")
    @classmethod
    def validate_semver(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(f"version must be MAJOR.MINOR.PATCH, got {v!r}")
        return v


class ContractSummary(BaseModel):
    contract_id: str
    version: str
    owner: str
    description: str


class BreakingChange(BaseModel):
    field: str
    change_type: Literal["removed", "type_changed", "renamed"]
    detail: str


class ContractDiff(BaseModel):
    contract_id: str
    from_version: str
    to_version: str
    breaking_changes: list[BreakingChange]
    minor_changes: list[str]
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: all 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_models.py src/pipelineguard/contracts/models.py
git commit -m "feat: Pydantic v2 contract models with semver validation"
```

---

## Task 3: Semver Versioning Logic

**Files:**
- Create: `tests/test_versioning.py`
- Create: `src/pipelineguard/contracts/versioning.py`

- [ ] **Step 1: Write failing tests**

`tests/test_versioning.py`:
```python
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
    assert diff.breaking_changes[0].field == "price"

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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_versioning.py -v
```

Expected: `ImportError: cannot import name 'parse_version'`

- [ ] **Step 3: Write `src/pipelineguard/contracts/versioning.py`**

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipelineguard.contracts.models import DataContract, ContractDiff


def parse_version(v: str) -> tuple[int, int, int]:
    major, minor, patch = v.split(".")
    return (int(major), int(minor), int(patch))


def latest_version(versions: list[str]) -> str:
    return max(versions, key=parse_version)


def classify_diff(old: "DataContract", new: "DataContract") -> "ContractDiff":
    from pipelineguard.contracts.models import BreakingChange, ContractDiff

    old_fields = {f.name: f for f in old.schema_spec.fields}
    new_fields = {f.name: f for f in new.schema_spec.fields}

    breaking: list[BreakingChange] = []
    minor: list[str] = []

    for name, field in old_fields.items():
        if name not in new_fields:
            breaking.append(BreakingChange(
                field=name,
                change_type="removed",
                detail=f"field '{name}' removed",
            ))
        elif new_fields[name].type != field.type:
            breaking.append(BreakingChange(
                field=name,
                change_type="type_changed",
                detail=(
                    f"field '{name}' type changed from "
                    f"{field.type!r} to {new_fields[name].type!r}"
                ),
            ))

    for name in new_fields:
        if name not in old_fields:
            minor.append(f"field '{name}' added (type: {new_fields[name].type})")

    return ContractDiff(
        contract_id=old.contract_id,
        from_version=old.version,
        to_version=new.version,
        breaking_changes=breaking,
        minor_changes=minor,
    )


def validate_bump(
    old_version: str, new_version: str, diff: "ContractDiff"
) -> str | None:
    old_maj = parse_version(old_version)[0]
    new_maj = parse_version(new_version)[0]

    if diff.breaking_changes and new_maj <= old_maj:
        return (
            f"breaking changes detected but version bump is not major "
            f"({old_version} -> {new_version}). "
            f"Consider bumping to {old_maj + 1}.0.0"
        )
    return None
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_versioning.py -v
```

Expected: all 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_versioning.py src/pipelineguard/contracts/versioning.py
git commit -m "feat: semver versioning — parse, latest, classify_diff, validate_bump"
```

---

## Task 4: ContractRegistry

**Files:**
- Create: `tests/test_registry.py`
- Create: `src/pipelineguard/contracts/registry.py`

- [ ] **Step 1: Write failing tests**

`tests/test_registry.py`:
```python
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
    write_patch = write(tmp_path, "patch.yaml", V1_PATCH_YAML)
    write_v1 = write(tmp_path, "v1.yaml", V1_YAML)
    registry.register(write_patch)
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
    assert diff.breaking_changes[0].field == "price"


def test_register_warns_on_invalid_semver_bump(registry, tmp_path):
    registry.register(write(tmp_path, "v1.yaml", V1_YAML))
    # V2_BREAKING_YAML removes a field but uses minor bump format — expect warning
    minor_breaking = V2_BREAKING_YAML.replace("version: 2.0.0", "version: 1.1.0")
    path = write(tmp_path, "v1_1_breaking.yaml", minor_breaking)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        registry.register(path)
    assert any("major" in str(w.message).lower() for w in caught)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_registry.py -v
```

Expected: `ImportError: cannot import name 'ContractRegistry'`

- [ ] **Step 3: Write `src/pipelineguard/contracts/registry.py`**

```python
from __future__ import annotations
import warnings
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pipelineguard._db import get_connection
from pipelineguard.contracts.models import DataContract, ContractSummary, ContractDiff
from pipelineguard.contracts.versioning import classify_diff, latest_version, validate_bump
from pipelineguard.exceptions import ContractNotFound, ContractVersionExists


class ContractRegistry:
    def __init__(self, db_path: str = "./pipelineguard.db") -> None:
        self._db_path = db_path
        conn = get_connection(db_path)
        conn.close()

    def register(self, yaml_path: str) -> DataContract:
        raw = Path(yaml_path).read_text()
        contract = DataContract.model_validate(yaml.safe_load(raw))

        conn = get_connection(self._db_path)
        try:
            existing = conn.execute(
                "SELECT 1 FROM contracts WHERE contract_id = ? AND version = ?",
                (contract.contract_id, contract.version),
            ).fetchone()
            if existing:
                raise ContractVersionExists(
                    f"{contract.contract_id} version {contract.version} already registered"
                )

            prior_rows = conn.execute(
                "SELECT version FROM contracts WHERE contract_id = ?",
                (contract.contract_id,),
            ).fetchall()
            if prior_rows:
                prior_latest = latest_version([r["version"] for r in prior_rows])
                prior_contract = self._load_version(conn, contract.contract_id, prior_latest)
                diff = classify_diff(prior_contract, contract)
                warning_msg = validate_bump(prior_latest, contract.version, diff)
                if warning_msg:
                    warnings.warn(warning_msg, stacklevel=2)

            conn.execute(
                """INSERT INTO contracts
                       (contract_id, version, owner, description, yaml_content, registered_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    contract.contract_id,
                    contract.version,
                    contract.owner,
                    contract.description,
                    raw,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return contract

    def load(self, contract_id: str, version: str | None = None) -> DataContract:
        conn = get_connection(self._db_path)
        try:
            if version is None:
                rows = conn.execute(
                    "SELECT version FROM contracts WHERE contract_id = ?",
                    (contract_id,),
                ).fetchall()
                if not rows:
                    raise ContractNotFound(f"contract '{contract_id}' not found")
                version = latest_version([r["version"] for r in rows])
            return self._load_version(conn, contract_id, version)
        finally:
            conn.close()

    def list(self) -> list[ContractSummary]:
        conn = get_connection(self._db_path)
        try:
            rows = conn.execute(
                "SELECT contract_id, version, owner, description FROM contracts"
                " ORDER BY contract_id, version"
            ).fetchall()
            return [
                ContractSummary(
                    contract_id=r["contract_id"],
                    version=r["version"],
                    owner=r["owner"],
                    description=r["description"],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def diff(self, contract_id: str, from_version: str, to_version: str) -> ContractDiff:
        conn = get_connection(self._db_path)
        try:
            old = self._load_version(conn, contract_id, from_version)
            new = self._load_version(conn, contract_id, to_version)
        finally:
            conn.close()
        return classify_diff(old, new)

    def _load_version(self, conn, contract_id: str, version: str) -> DataContract:
        row = conn.execute(
            "SELECT yaml_content FROM contracts WHERE contract_id = ? AND version = ?",
            (contract_id, version),
        ).fetchone()
        if not row:
            raise ContractNotFound(
                f"contract '{contract_id}' version {version} not found"
            )
        return DataContract.model_validate(yaml.safe_load(row["yaml_content"]))
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_registry.py -v
```

Expected: all 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_registry.py src/pipelineguard/contracts/registry.py
git commit -m "feat: SQLite-backed ContractRegistry — register, load, list, diff"
```

---

## Task 5: CLI Scaffold

**Files:**
- Create: `tests/test_cli.py`
- Create: `src/pipelineguard/cli/main.py`

- [ ] **Step 1: Write failing tests**

`tests/test_cli.py`:
```python
import pytest
from typer.testing import CliRunner
from pipelineguard.cli.main import app

runner = CliRunner()

V1_YAML = """\
contract_id: test_contract
version: 1.0.0
owner: test-owner
description: CLI test contract
schema:
  fields:
    - name: price
      type: float
      nullable: false
"""

V2_YAML = """\
contract_id: test_contract
version: 2.0.0
owner: test-owner
description: CLI test contract v2
schema:
  fields:
    - name: price
      type: float
      nullable: false
    - name: store
      type: string
      nullable: true
"""


@pytest.fixture
def yaml_files(tmp_path):
    v1 = tmp_path / "v1.yaml"
    v1.write_text(V1_YAML)
    v2 = tmp_path / "v2.yaml"
    v2.write_text(V2_YAML)
    return {"v1": str(v1), "v2": str(v2), "db": str(tmp_path / "test.db")}


def test_register_exits_zero(yaml_files):
    result = runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    assert result.exit_code == 0
    assert "test_contract" in result.output


def test_register_duplicate_exits_nonzero(yaml_files):
    runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    result = runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    assert result.exit_code != 0


def test_list_shows_contract_id_and_version(yaml_files):
    runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    result = runner.invoke(app, ["contract", "list", "--db", yaml_files["db"]])
    assert result.exit_code == 0
    assert "test_contract" in result.output
    assert "1.0.0" in result.output


def test_list_empty_db_exits_zero(yaml_files):
    result = runner.invoke(app, ["contract", "list", "--db", yaml_files["db"]])
    assert result.exit_code == 0


def test_show_after_register(yaml_files):
    runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    result = runner.invoke(app, ["contract", "show", "test_contract", "--db", yaml_files["db"]])
    assert result.exit_code == 0
    assert "test_contract" in result.output
    assert "test-owner" in result.output


def test_show_missing_contract_exits_nonzero(yaml_files):
    result = runner.invoke(app, ["contract", "show", "nonexistent", "--db", yaml_files["db"]])
    assert result.exit_code != 0


def test_diff_shows_added_field(yaml_files):
    runner.invoke(app, ["contract", "register", yaml_files["v1"], "--db", yaml_files["db"]])
    runner.invoke(app, ["contract", "register", yaml_files["v2"], "--db", yaml_files["db"]])
    result = runner.invoke(
        app,
        ["contract", "diff", "test_contract", "--from", "1.0.0", "--to", "2.0.0", "--db", yaml_files["db"]],
    )
    assert result.exit_code == 0
    assert "store" in result.output


@pytest.mark.parametrize("cmd", ["validate", "drift", "quarantine", "tune", "dashboard"])
def test_stubs_exit_zero_and_print_not_implemented(cmd):
    result = runner.invoke(app, [cmd])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_cli.py -v
```

Expected: `ImportError: cannot import name 'app' from 'pipelineguard.cli.main'`

- [ ] **Step 3: Write `src/pipelineguard/cli/main.py`**

```python
import typer
from pipelineguard.contracts.registry import ContractRegistry
from pipelineguard.exceptions import ContractNotFound, ContractVersionExists

app = typer.Typer(name="pg", help="PipelineGuard — ML pipeline data contract engine")
contract_app = typer.Typer(help="Manage data contracts")
app.add_typer(contract_app, name="contract")

_DB = typer.Option("./pipelineguard.db", "--db", help="Path to PipelineGuard database")


@contract_app.command("list")
def contract_list(db: str = _DB):
    """List all registered contracts."""
    registry = ContractRegistry(db_path=db)
    summaries = registry.list()
    if not summaries:
        typer.echo("No contracts registered.")
        return
    for s in summaries:
        typer.echo(f"{s.contract_id}  {s.version}  {s.owner}  {s.description}")


@contract_app.command("show")
def contract_show(
    contract_id: str,
    version: str = typer.Option(None, "--version", help="Specific version (default: latest)"),
    db: str = _DB,
):
    """Show a contract."""
    registry = ContractRegistry(db_path=db)
    try:
        contract = registry.load(contract_id, version)
    except ContractNotFound as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{contract.contract_id}  v{contract.version}")
    typer.echo(f"Owner: {contract.owner}")
    typer.echo(f"Description: {contract.description}")
    typer.echo(f"Fields ({len(contract.schema_spec.fields)}):")
    for field in contract.schema_spec.fields:
        typer.echo(f"  {field.name}  {field.type}  nullable={field.nullable}")


@contract_app.command("register")
def contract_register(path: str, db: str = _DB):
    """Register a contract from a YAML file."""
    registry = ContractRegistry(db_path=db)
    try:
        contract = registry.register(path)
        typer.echo(f"Registered {contract.contract_id} v{contract.version}")
    except ContractVersionExists as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@contract_app.command("diff")
def contract_diff(
    contract_id: str,
    from_version: str = typer.Option(..., "--from"),
    to_version: str = typer.Option(..., "--to"),
    db: str = _DB,
):
    """Diff two versions of a contract."""
    registry = ContractRegistry(db_path=db)
    try:
        diff = registry.diff(contract_id, from_version, to_version)
    except ContractNotFound as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    if diff.breaking_changes:
        typer.echo(f"{len(diff.breaking_changes)} breaking change(s):")
        for bc in diff.breaking_changes:
            typer.echo(f"  BREAKING  {bc.field}: {bc.detail}")
    if diff.minor_changes:
        typer.echo(f"{len(diff.minor_changes)} non-breaking change(s):")
        for mc in diff.minor_changes:
            typer.echo(f"  +  {mc}")
    if not diff.breaking_changes and not diff.minor_changes:
        typer.echo("No changes detected.")


@app.command()
def validate():
    """[Phase 1] Validate a dataset against a contract."""
    typer.echo("[Phase 1] not yet implemented")
    raise typer.Exit(code=0)


@app.command()
def drift():
    """[Phase 2] Show drift history."""
    typer.echo("[Phase 2] not yet implemented")
    raise typer.Exit(code=0)


@app.command()
def quarantine():
    """[Phase 3] Manage quarantined batches."""
    typer.echo("[Phase 3] not yet implemented")
    raise typer.Exit(code=0)


@app.command()
def tune():
    """[Phase 2] Tune drift thresholds."""
    typer.echo("[Phase 2] not yet implemented")
    raise typer.Exit(code=0)


@app.command()
def dashboard():
    """[Phase 5] Launch Streamlit dashboard."""
    typer.echo("[Phase 5] not yet implemented")
    raise typer.Exit(code=0)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_cli.py -v
```

Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py src/pipelineguard/cli/main.py
git commit -m "feat: Typer CLI scaffold — contract commands and phase stubs"
```

---

## Task 6: Public API Exports + Milestone Verification

**Files:**
- Modify: `src/pipelineguard/__init__.py`
- Create: `contracts/ecommerce_price.yaml`

- [ ] **Step 1: Fill in `src/pipelineguard/__init__.py`**

```python
from pipelineguard.contracts.models import DataContract, ContractSummary, ContractDiff
from pipelineguard.contracts.registry import ContractRegistry
from pipelineguard.exceptions import (
    PipelineGuardError,
    ContractNotFound,
    ContractVersionExists,
    InvalidSemverBump,
)

__all__ = [
    "DataContract",
    "ContractSummary",
    "ContractDiff",
    "ContractRegistry",
    "PipelineGuardError",
    "ContractNotFound",
    "ContractVersionExists",
    "InvalidSemverBump",
]
```

- [ ] **Step 2: Write `contracts/ecommerce_price.yaml`**

```yaml
contract_id: product_price_v2
version: 2.0.0
owner: el-gorrim-mohamed
description: Scraped product prices from Moroccan e-commerce stores

schema:
  fields:
    - name: product_id
      type: string
      nullable: false
      pattern: '^[A-Z0-9]{8,16}$'

    - name: price_mad
      type: float
      nullable: false
      min: 0.01
      max: 500000.0

    - name: store_id
      type: string
      nullable: false
      allowed_values: [jumia, hmizate, avito, marjane]

    - name: scraped_at
      type: timestamp
      nullable: false

statistics:
  price_mad:
    expected_distribution: lognormal
    drift_sensitivity: medium
    outlier_zscore: 4.0
  completeness:
    min_row_count: 100
    max_null_fraction: 0.02

freshness:
  max_delay_minutes: 60

remediation:
  on_schema_violation: quarantine
  on_drift_violation: alert_and_continue
  on_freshness_violation: alert
  alert_channels: [slack_webhook, email]
  suppression_window_minutes: 30
```

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS (test_models, test_versioning, test_registry, test_cli)

- [ ] **Step 4: Verify milestone — register and inspect the example contract**

```bash
pg contract register contracts/ecommerce_price.yaml
```

Expected output:
```
Registered product_price_v2 v2.0.0
```

```bash
pg contract show product_price_v2
```

Expected output:
```
product_price_v2  v2.0.0
Owner: el-gorrim-mohamed
Description: Scraped product prices from Moroccan e-commerce stores
Fields (4):
  product_id  string  nullable=False
  price_mad  float  nullable=False
  store_id  string  nullable=False
  scraped_at  timestamp  nullable=False
```

```bash
pg contract list
```

Expected: one row showing `product_price_v2  2.0.0  el-gorrim-mohamed`

- [ ] **Step 5: Verify public API import**

```bash
python -c "from pipelineguard import ContractRegistry, DataContract; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/pipelineguard/__init__.py contracts/ecommerce_price.yaml
git commit -m "feat: public API exports and example ecommerce contract — Phase 0 milestone complete"
```

---

## Phase 0 Complete

All deliverables from the spec:

| Deliverable | Status |
|---|---|
| Contract YAML schema | `contracts/ecommerce_price.yaml` |
| Pydantic v2 models | `src/pipelineguard/contracts/models.py` |
| SQLite registry | `src/pipelineguard/contracts/registry.py` |
| CLI scaffold | `src/pipelineguard/cli/main.py` |
| pytest suite | `tests/` — 35+ tests |

Milestone achieved: `pg contract register contracts/ecommerce_price.yaml` succeeds, `pg contract show product_price_v2` prints correct output, full test suite passes.
