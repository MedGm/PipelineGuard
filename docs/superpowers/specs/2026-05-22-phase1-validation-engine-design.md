# PipelineGuard — Phase 1: Validation Engine Design

**Date:** 2026-05-22
**Scope:** Phase 1 — full validation engine (schema + statistical validators, DuckDB result store, `pg validate --explain`)
**Status:** Approved, ready for implementation

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Input format | pandas DataFrame + Parquet file | Covers 90% of real use; Polars/JSON deferred |
| Validator architecture | Protocol-based plugins | Each validator independently testable; clean extension point |
| Execution model | Synchronous | asyncio adds no benefit for CPU-bound pandas at <2s target |
| Statistical baseline | First batch auto-bootstraps | No manual setup; zero friction for new contracts |
| Result persistence | Always (even on FAIL) | Operator needs history to investigate failures |

---

## File Structure

New files:
```
src/pipelineguard/
├── validators/
│   ├── __init__.py
│   ├── base.py          # ValidatorPlugin protocol, Violation, ValidationResult
│   ├── schema.py        # 7 schema validator classes
│   ├── statistical.py   # 5 statistical validator classes
│   └── engine.py        # Validator — orchestrates plugins, stores results
├── store/
│   ├── __init__.py
│   └── observations.py  # DuckDB: init schema, write/read runs/violations/field_stats
```

Modified files:
- `src/pipelineguard/__init__.py` — add `Validator`, `ValidationResult`, `Violation`
- `src/pipelineguard/cli/main.py` — implement `pg validate` (currently a stub)
- `tests/conftest.py` — add `obs_db_path`, `sample_parquet` fixtures
- `pyproject.toml` — add `scipy`, `pandas`, `numpy`, `pyarrow` to dependencies

New test files:
```
tests/
├── test_schema_validators.py
├── test_statistical_validators.py
├── test_validator_engine.py
├── test_observations_store.py
└── test_validate_cli.py
```

---

## Validation Models (`validators/base.py`)

```python
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, Protocol
import pandas as pd
from pydantic import BaseModel
from pipelineguard.contracts.models import DataContract

class Violation(BaseModel):
    field: Optional[str] = None        # None = batch-level (e.g. row_count)
    validator: str                     # e.g. "range_check", "ks_test"
    severity: Literal["WARN", "FAIL"]
    message: str
    affected_rows: Optional[int] = None
    metric: Optional[float] = None     # p-value, PSI score, z-score, etc.
    threshold: Optional[float] = None
    suggestion: Optional[str] = None

class ValidationResult(BaseModel):
    run_id: str                        # uuid4
    contract_id: str
    contract_version: str
    batch_id: str                      # uuid4 unless caller supplies one
    timestamp: datetime
    status: Literal["PASS", "WARN", "FAIL"]
    row_count: int
    duration_ms: float
    violations: list[Violation]

class ValidatorPlugin(Protocol):
    name: str
    def check(
        self,
        df: pd.DataFrame,
        contract: DataContract,
        baselines: dict[str, "FieldStats | None"] | None = None,
    ) -> list[Violation]: ...
```

**Status derivation rule:** `FAIL` if any violation has `severity == "FAIL"`. `WARN` if any `WARN` and no `FAIL`. `PASS` otherwise.

`Violation` lives in `validators/base.py`, not `contracts/models.py` — it is a runtime result, not a contract definition.

---

## Schema Validators (`validators/schema.py`)

Seven classes implementing `ValidatorPlugin`. Each checks one concern.

| Class | `name` | Severity | Contract field(s) |
|---|---|---|---|
| `TypeValidator` | `"type_check"` | FAIL | `field.type` |
| `NullableValidator` | `"nullable_check"` | FAIL | `field.nullable` (zero nulls if False); `contract.statistics["completeness"]["max_null_fraction"]` (fraction cap if nullable=True and key present) |
| `PatternValidator` | `"pattern_check"` | FAIL | `field.pattern` |
| `AllowedValuesValidator` | `"allowed_values_check"` | FAIL | `field.allowed_values` |
| `RangeValidator` | `"range_check"` | FAIL | `field.min`, `field.max` |
| `RowCountValidator` | `"row_count_check"` | FAIL | `statistics.completeness.min_row_count` |
| `FreshnessValidator` | `"freshness_check"` | WARN | `contract.freshness.max_delay_minutes` |

**Type compatibility matrix** (no coercion):

| Contract type | Accepted pandas dtypes |
|---|---|
| `string` | `object`, `string` |
| `integer` | `int8/16/32/64`, `Int8/16/32/64` |
| `float` | `float32/64`, `int*` (widening allowed) |
| `boolean` | `bool` |
| `timestamp` | `datetime64[*]` |

**Skipping rules:**
- If a contract field is absent from the DataFrame: `TypeValidator` emits FAIL; all other validators skip that field (no duplicate violations).
- `RowCountValidator`: skipped if `statistics.completeness.min_row_count` absent from contract.
- `FreshnessValidator`: skipped if `contract.freshness` is None.
- `PatternValidator`: skipped for fields without `pattern`.
- `AllowedValuesValidator`: skipped for fields without `allowed_values`.
- `RangeValidator`: skipped for fields without `min` or `max`.

**`affected_rows`**: populated for `PatternValidator`, `AllowedValuesValidator`, `RangeValidator`. Others leave it `None`.

---

## Statistical Validators (`validators/statistical.py`)

Five classes. All receive `baselines: dict[str, FieldStats | None]` from the engine.

**Bootstrap rule:** If `baselines[field_name] is None` (first run), the validator returns no violations. Stats are stored as the new baseline after the run completes.

| Class | `name` | Method | Trigger | Severity |
|---|---|---|---|---|
| `KSTestValidator` | `"ks_test"` | `scipy.stats.ks_2samp` | p < α(sensitivity) | WARN |
| `ChiSquaredValidator` | `"chi_squared_test"` | `scipy.stats.chisquare` | p < α(sensitivity) | WARN |
| `ZScoreValidator` | `"z_score_check"` | per-record z-score | \|z\| > `outlier_zscore` | WARN |
| `PSIValidator` | `"psi_check"` | Population Stability Index | PSI > 0.10 → WARN; PSI > 0.20 → FAIL | WARN/FAIL |
| `CompletenessValidator` | `"completeness_drift"` | null fraction vs baseline | increase > 0.05 absolute | WARN |

**Sensitivity → α mapping:**

| Sensitivity | KS α | PSI warn threshold |
|---|---|---|
| `low` | 0.001 | 0.25 |
| `medium` (default) | 0.05 | 0.10 |
| `high` | 0.10 | 0.05 |

**Scoping rules:**
- `KSTestValidator` / `PSIValidator`: only fields with `drift_sensitivity` in `contract.statistics`; only `float`/`integer` type.
- `ChiSquaredValidator`: only fields with `drift_sensitivity`; only `string` type; skipped if any expected bucket has < 5 observations.
- `ZScoreValidator`: only fields with `outlier_zscore` in `contract.statistics`; only `float`/`integer` type.
- `CompletenessValidator`: all fields (no contract.statistics annotation required).

**PSI formula:**
```python
PSI = Σ (Aᵢ − Eᵢ) × ln(Aᵢ / Eᵢ)
```
where Aᵢ = actual (current) fraction, Eᵢ = expected (baseline) fraction in bucket i. 10 percentile-based bins. Epsilon clip to avoid ln(0).

---

## DuckDB Observations Store (`store/observations.py`)

Three tables in `observations.duckdb`:

```sql
CREATE TABLE IF NOT EXISTS validation_runs (
    run_id           TEXT PRIMARY KEY,
    contract_id      TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    batch_id         TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    status           TEXT NOT NULL,
    row_count        INTEGER NOT NULL,
    duration_ms      REAL NOT NULL,
    violation_count  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS violations (
    run_id        TEXT NOT NULL,
    field         TEXT,
    validator     TEXT NOT NULL,
    severity      TEXT NOT NULL,
    message       TEXT NOT NULL,
    affected_rows INTEGER,
    metric        REAL,
    threshold     REAL,
    suggestion    TEXT
);

CREATE TABLE IF NOT EXISTS field_stats (
    run_id        TEXT NOT NULL,
    contract_id   TEXT NOT NULL,
    field_name    TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    row_count     INTEGER NOT NULL,
    null_fraction REAL NOT NULL,
    mean          REAL,        -- NULL for string/boolean
    std           REAL,
    min_val       REAL,
    max_val       REAL,
    p25           REAL,
    p50           REAL,
    p75           REAL,
    value_counts  TEXT         -- JSON {"val": fraction, ...}; NULL for numeric
);
```

**`ObservationsStore` public API:**

```python
class ObservationsStore:
    def __init__(self, db_path: str = "./observations.duckdb") -> None: ...

    def write_run(self, result: ValidationResult) -> None:
        # Inserts into validation_runs + violations

    def write_field_stats(
        self, run_id: str, contract_id: str, stats: list[FieldStats]
    ) -> None:
        # Inserts into field_stats

    def get_baseline(
        self, contract_id: str, field_name: str
    ) -> FieldStats | None:
        # Returns most recent field_stats row for contract+field
        # Returns None if no prior run (bootstrap)

    def get_run(self, run_id: str) -> ValidationResult | None: ...

    def list_runs(
        self, contract_id: str, limit: int = 20
    ) -> list[RunSummary]: ...
```

`FieldStats` is a dataclass defined in `validators/base.py` (not `store/observations.py`) so that statistical validators can import it without creating a circular dependency. `store/observations.py` imports `FieldStats` and `ValidationResult` from `validators/base.py`; nothing in `validators/` imports from `store/`.

```python
@dataclass
class FieldStats:
    run_id: str
    contract_id: str
    field_name: str
    timestamp: str
    row_count: int
    null_fraction: float
    mean: float | None = None
    std: float | None = None
    min_val: float | None = None
    max_val: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    value_counts: dict[str, float] | None = None  # {value: fraction}
```

`RunSummary` is a lightweight Pydantic model (run_id, contract_id, timestamp, status, row_count, violation_count) for `list_runs`.

Default paths: `./observations.duckdb` (CWD convention, same as `pipelineguard.db`). Both configurable via CLI flags.

---

## Validator Engine (`validators/engine.py`)

```python
class Validator:
    def __init__(
        self,
        contract: DataContract,
        obs_store: ObservationsStore | None = None,
        obs_db_path: str = "./observations.duckdb",
    ) -> None:
        self._contract = contract
        self._store = obs_store or ObservationsStore(obs_db_path)
        self._schema_plugins: list[ValidatorPlugin] = [
            TypeValidator(), NullableValidator(), PatternValidator(),
            AllowedValuesValidator(), RangeValidator(),
            RowCountValidator(), FreshnessValidator(),
        ]
        self._stat_plugins: list[ValidatorPlugin] = [
            KSTestValidator(), ChiSquaredValidator(), ZScoreValidator(),
            PSIValidator(), CompletenessValidator(),
        ]

    def validate(
        self,
        df: pd.DataFrame,
        batch_id: str | None = None,
    ) -> ValidationResult:
        # 1. Compute field stats
        # 2. Fetch baselines
        # 3. Run schema plugins → collect violations
        # 4. Run statistical plugins with baselines → collect violations
        # 5. Derive status (FAIL > WARN > PASS)
        # 6. Build ValidationResult
        # 7. Persist run + violations + field_stats (always, even on FAIL)
        # 8. Return result
```

`_compute_field_stats(df, contract, run_id) -> list[FieldStats]` is a module-level helper. Iterates `contract.schema_spec.fields` only (ignores extra DataFrame columns not in the contract), computes:
- `null_fraction` for all fields
- `mean/std/min/max/p25/p50/p75` for `float`/`integer` fields
- `value_counts` (top-10 by frequency, as fraction of total) for `string` fields

Statistical plugins receive `baselines: dict[str, FieldStats | None]` as third argument. Schema plugins ignore it (defaults to `None`).

---

## CLI: `pg validate`

```
pg validate --contract <contract_id> \
            --file <path.parquet> \
            [--explain] \
            [--batch-id <id>] \
            [--db <pipelineguard.db path>] \
            [--obs <observations.duckdb path>]
```

**Compact output (without `--explain`):**
```
[FAIL] price_mad :: range_check  (247 rows out of range)
[WARN] price_mad :: ks_test  (p=0.003, threshold=0.050)
[PASS] store_id :: allowed_values
[PASS] product_id :: pattern
[PASS] scraped_at :: freshness

Status: WARN  |  Run ID: run-8f3a2c  |  1.24s  |  12,847 rows
```

**Verbose output (with `--explain`):**
```
[WARN] price_mad :: ks_test
  Current distribution differs from reference window.
  KS statistic: 0.142  (threshold: 0.100)
  p-value: 0.003  (alpha: 0.050)
  -> Run `pg tune --contract product_price_v2 --field price_mad` to evaluate threshold.

[PASS] ...
```

**Exit codes:**
| Code | Meaning |
|---|---|
| `0` | PASS or WARN |
| `1` | FAIL (data violation) |
| `2` | Error (contract not found, file unreadable, etc.) |

Exit code 0 for WARN allows CI pipelines to gate on FAIL only, while still surfacing warnings in output.

---

## Test Plan

### `tests/conftest.py` additions

```python
@pytest.fixture
def obs_db_path(tmp_path) -> str:
    return str(tmp_path / "test_obs.duckdb")

@pytest.fixture
def sample_parquet(tmp_path) -> str:
    # Creates a valid ecommerce-shaped Parquet file:
    # product_id (string), price_mad (float), store_id (string), scraped_at (datetime)
    # Returns path as str
```

### `test_schema_validators.py` (unit, no I/O)

- `TypeValidator`: int64 vs `float` contract = PASS (widening); object vs `float` = FAIL; missing column = FAIL
- `NullableValidator`: null fraction 0.01 on nullable field = PASS; any null on non-nullable = FAIL
- `PatternValidator`: all match regex = PASS; 3 mismatches = FAIL with `affected_rows=3`; skipped if no pattern in contract
- `AllowedValuesValidator`: unknown category = FAIL; all valid = PASS
- `RangeValidator`: boundary value = PASS; out-of-range value = FAIL with `affected_rows`; skipped if no min/max
- `RowCountValidator`: `len(df) >= min_row_count` = PASS; below = FAIL; skipped if no completeness in contract
- `FreshnessValidator`: timestamp 30min ago, max_delay=60 = PASS; 90min ago = WARN; skipped if no freshness

### `test_statistical_validators.py` (unit, numpy random seeded)

- `KSTestValidator`: same distribution (seed=42) = no violation; mean shifted by σ=1.5 = WARN
- `KSTestValidator`: baseline=None → no violation (bootstrap)
- `KSTestValidator`: sensitivity `low` → higher α threshold needed to trigger
- `PSIValidator`: same distribution = PASS; heavily shifted = FAIL (PSI > 0.20)
- `PSIValidator`: moderately shifted = WARN (PSI 0.10–0.20)
- `ZScoreValidator`: clean data (z < 3) = no violations; value at 5σ = WARN
- `ChiSquaredValidator`: same distribution = no violation; shifted categorical = WARN; skipped if bucket < 5
- `CompletenessValidator`: null fraction unchanged = no violation; +0.10 increase = WARN; baseline=None → no violation

### `test_validator_engine.py` (integration, tmp DuckDB)

- Clean DataFrame → PASS, result persisted in DuckDB
- DataFrame with out-of-range values → FAIL, result persisted
- FAIL > WARN > PASS status derivation
- Second `validate()` call uses first run as baseline (statistical validators now compare)
- `result.run_id` unique per call
- `result.duration_ms > 0`
- `result.row_count == len(df)`

### `test_observations_store.py` (unit, tmp DuckDB)

- `write_run` + `get_run` round-trips `ValidationResult` (including violations)
- `get_baseline` returns `None` on first call
- `get_baseline` returns `FieldStats` after `write_field_stats`
- `list_runs` returns most recent first, respects `limit`
- `list_runs` on unknown contract_id returns `[]`

### `test_validate_cli.py` (CLI, CliRunner + tmp Parquet)

- `pg validate --contract X --file Y.parquet` exits 0 on PASS
- `pg validate` on data with FAIL violation exits 1
- `--explain` flag adds suggestion text to output
- Missing contract exits 2
- Unreadable file path exits 2
- `--obs` flag routes DuckDB to tmp path (test isolation)

---

## Phase 1 Success Criterion (from spec)

> Full validation run on real price data produces actionable output.

Milestone: `pg validate --contract product_price_v2 --file data/sample.parquet --explain` produces per-field PASS/WARN/FAIL output with human-readable messages and suggestions. 53 existing tests still pass.
