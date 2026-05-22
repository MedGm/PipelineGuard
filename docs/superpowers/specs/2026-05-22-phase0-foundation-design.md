# PipelineGuard — Phase 0: Foundation Design

**Date:** 2026-05-22
**Scope:** Phase 0 only (contract schema, Pydantic models, SQLite registry, CLI scaffold, pytest suite)
**Status:** Approved, ready for implementation

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Python layout | `src/` layout | Avoids import confusion, clean `pip install -e .` |
| Pydantic version | v2 | Current standard, faster validation |
| Registry backend | SQLite-backed (Option B) | SQLite is Phase 0 scope; avoids retrofit in Phase 1 |
| DB access layer | Raw `sqlite3` (stdlib) | Zero extra deps, aligns with minimal-dependency constraint |

---

## Package Structure

```
pipelineguard/
├── src/
│   └── pipelineguard/
│       ├── __init__.py              # exports ContractRegistry, DataContract
│       ├── _db.py                   # sqlite3 connection + schema init
│       ├── contracts/
│       │   ├── __init__.py
│       │   ├── models.py            # Pydantic v2 models
│       │   ├── registry.py          # ContractRegistry
│       │   └── versioning.py        # semver enforcement + diff logic
│       └── cli/
│           ├── __init__.py
│           └── main.py              # Typer app, `pg` entrypoint
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_registry.py
│   └── test_cli.py
├── contracts/
│   └── ecommerce_price.yaml         # example contract
├── pyproject.toml
└── README.md
```

`pg` entry point in `pyproject.toml`:
```toml
[project.scripts]
pg = "pipelineguard.cli.main:app"
```

Future `api/` and `dashboard/` go alongside `cli/` inside the package. Top-level `contracts/` dir holds example contracts only.

---

## Pydantic v2 Models (`contracts/models.py`)

```python
from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re

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
    on_schema_violation: Literal["quarantine", "alert", "soft_block", "alert_and_continue"] = "alert"
    on_drift_violation: Literal["quarantine", "alert", "soft_block", "alert_and_continue"] = "alert_and_continue"
    on_freshness_violation: Literal["quarantine", "alert", "soft_block", "alert_and_continue"] = "alert"
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
```

Notes:
- `schema` is reserved in Pydantic v2 → aliased as `schema_spec` internally, `schema` in YAML/JSON.
- `statistics` is `dict[str, Any]` in Phase 0. Fully typed in Phase 1 when validators consume it.

---

## SQLite Schema (`_db.py`)

```sql
CREATE TABLE IF NOT EXISTS contracts (
    contract_id   TEXT NOT NULL,
    version       TEXT NOT NULL,
    owner         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    yaml_content  TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    PRIMARY KEY (contract_id, version)
);
```

`_db.py` exposes one function: `get_connection(db_path: str) -> sqlite3.Connection`. Registry opens and closes a connection per call. No pooling in Phase 0.

---

## ContractRegistry (`contracts/registry.py`)

```python
class ContractRegistry:
    def __init__(self, db_path: str = "./pipelineguard.db") -> None:
        # calls _db.get_connection to init schema on first use

    def register(self, yaml_path: str) -> DataContract:
        # 1. Read and parse YAML
        # 2. Validate via DataContract (raises ValidationError on bad schema)
        # 3. Check version doesn't already exist (raises ContractVersionExists)
        # 4. Warn if new version is not a valid semver bump over latest
        # 5. INSERT into contracts table
        # 6. Return parsed DataContract

    def load(self, contract_id: str, version: str | None = None) -> DataContract:
        # version=None → latest (sorted by `(major, minor, patch)` integer tuple via `parse_version()`, not insertion-order)
        # raises ContractNotFound if missing

    def list(self) -> list[ContractSummary]:
        # SELECT contract_id, version, owner, description
        # No YAML parse — uses stored columns only

    def diff(self, contract_id: str, from_version: str, to_version: str) -> ContractDiff:
        # Loads both versions, compares field-by-field
        # Returns ContractDiff(breaking_changes, minor_changes)
```

### ContractDiff model

```python
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

### Error hierarchy

```python
class PipelineGuardError(Exception): ...
class ContractNotFound(PipelineGuardError): ...
class ContractVersionExists(PipelineGuardError): ...
class InvalidSemverBump(PipelineGuardError): ...
```

`InvalidSemverBump` is raised internally by `validate_bump()` and caught by `register()`. Logged as a warning to stderr; registration still proceeds. Never propagated to the caller.

---

## Semver enforcement (`contracts/versioning.py`)

Rules from spec:

| Change | Bump required |
|---|---|
| Add optional field | Patch |
| Tighten/loosen statistical threshold | Minor |
| Change remediation policy | Minor |
| Remove field | Major |
| Change field type | Major |
| Rename field | Major (treated as remove + add) |

`versioning.py` exposes:
- `parse_version(v: str) -> tuple[int, int, int]`
- `latest_version(versions: list[str]) -> str` — sorted by `(major, minor, patch)` integer tuple via `parse_version()` max
- `classify_diff(old: DataContract, new: DataContract) -> ContractDiff` — used by `registry.diff()`
- `validate_bump(old_version: str, new_version: str, diff: ContractDiff) -> str | None` — returns warning message if bump level doesn't match changes, None if valid

---

## CLI scaffold (`cli/main.py`)

```python
app = typer.Typer(name="pg", help="PipelineGuard — ML pipeline data contract engine")
contract_app = typer.Typer(help="Manage data contracts")
app.add_typer(contract_app, name="contract")

# Phase 0: fully implemented
@contract_app.command("list")
def contract_list(db: str = "./pipelineguard.db"): ...

@contract_app.command("show")
def contract_show(contract_id: str, db: str = "./pipelineguard.db"): ...

@contract_app.command("register")
def contract_register(path: str, db: str = "./pipelineguard.db"): ...

@contract_app.command("diff")
def contract_diff(
    contract_id: str,
    from_version: str = typer.Option(..., "--from"),
    to_version: str   = typer.Option(..., "--to"),
    db: str = "./pipelineguard.db",
): ...

# Phase 1-5 stubs: visible in `pg --help`, print "not yet implemented" and exit 0
@app.command()
def validate():
    """[Phase 1] Validate a dataset against a contract."""
    typer.echo("[Phase 1] not yet implemented"); raise typer.Exit(code=0)

@app.command()
def drift():
    """[Phase 2] Show drift history."""
    typer.echo("[Phase 2] not yet implemented"); raise typer.Exit(code=0)

@app.command()
def quarantine():
    """[Phase 3] Manage quarantined batches."""
    typer.echo("[Phase 3] not yet implemented"); raise typer.Exit(code=0)

@app.command()
def tune():
    """[Phase 2] Tune drift thresholds."""
    typer.echo("[Phase 2] not yet implemented"); raise typer.Exit(code=0)

@app.command()
def dashboard():
    """[Phase 5] Launch Streamlit dashboard."""
    typer.echo("[Phase 5] not yet implemented"); raise typer.Exit(code=0)
```

`--db` flag on every command defaults to `./pipelineguard.db`. Overridable for tests and multi-project setups.

---

## Test Plan

### `conftest.py`
```python
@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")

@pytest.fixture
def sample_contract_yaml(tmp_path) -> str:
    # writes ecommerce_price.yaml to tmp_path, returns path
```

### `test_models.py` (unit, no I/O)
- Valid contract YAML round-trips through `DataContract`
- Invalid semver (`"1.0"`, `"v2.0.0"`) raises `ValidationError`
- Missing `contract_id` raises `ValidationError`
- `schema` alias works: `contract.schema_spec.fields` populated
- `FieldSpec` with `type="float"` + `min`/`max` parses correctly
- `RemediationSpec` defaults applied when key absent from YAML

### `test_registry.py` (uses `db_path` fixture)
- `register()` stores contract; `load()` retrieves identical model
- `register()` same version twice raises `ContractVersionExists`
- `load()` with `version=None` returns latest (sorted by `(major, minor, patch)` integer tuple via `parse_version()`, not insertion-order)
- `list()` returns `ContractSummary` list for all registered contracts
- `diff()` detects field removal as breaking change
- `diff()` detects type change as breaking change
- `diff()` detects added optional field as non-breaking

### `test_cli.py` (uses `CliRunner` + `db_path`)
- `pg contract register <yaml>` exits 0; contract loadable after
- `pg contract list` prints contract_id and version
- `pg contract show <id>` prints contract fields
- `pg contract diff <id> --from 1.0.0 --to 2.0.0` prints breaking changes
- Stub commands (`pg validate`, `pg drift`) exit without crashing

No Hypothesis in Phase 0. Added in Phase 1 for validator property tests.

---

## Phase 0 success criterion (from spec)

> Contracts load; schema validation passes on sample e-commerce dataset.

Milestone: `pg contract register contracts/ecommerce_price.yaml` succeeds, `pg contract show product_price_v2` prints correct output, full test suite passes.
