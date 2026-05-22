from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Protocol, runtime_checkable

import pandas as pd
from pydantic import BaseModel

from pipelineguard.contracts.models import DataContract


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
    value_counts: dict[str, float] | None = None
    sample_values: list[float] | None = None  # for KS/PSI tests


class Violation(BaseModel):
    field: Optional[str] = None
    validator: str
    severity: Literal["WARN", "FAIL"]
    message: str
    affected_rows: Optional[int] = None
    metric: Optional[float] = None
    threshold: Optional[float] = None
    suggestion: Optional[str] = None


class ValidationResult(BaseModel):
    run_id: str
    contract_id: str
    contract_version: str
    batch_id: str
    timestamp: datetime
    status: Literal["PASS", "WARN", "FAIL"]
    row_count: int
    duration_ms: float
    violations: list[Violation]


@runtime_checkable
class ValidatorPlugin(Protocol):
    name: str

    def check(
        self,
        df: pd.DataFrame,
        contract: DataContract,
        baselines: dict[str, FieldStats | None] | None = None,
    ) -> list[Violation]: ...
