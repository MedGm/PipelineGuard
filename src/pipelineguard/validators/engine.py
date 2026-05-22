from __future__ import annotations
import time
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd

from pipelineguard.contracts.models import DataContract
from pipelineguard.store.observations import ObservationsStore
from pipelineguard.validators.base import FieldStats, ValidationResult, Violation
from pipelineguard.validators.schema import (
    TypeValidator, NullableValidator, PatternValidator,
    AllowedValuesValidator, RangeValidator, RowCountValidator, FreshnessValidator,
)
from pipelineguard.validators.statistical import (
    KSTestValidator, ChiSquaredValidator, ZScoreValidator,
    PSIValidator, CompletenessValidator,
)


def _derive_status(violations: list[Violation]) -> str:
    if any(v.severity == "FAIL" for v in violations):
        return "FAIL"
    if any(v.severity == "WARN" for v in violations):
        return "WARN"
    return "PASS"


def _compute_field_stats(
    df: pd.DataFrame, contract: DataContract, run_id: str
) -> list[FieldStats]:
    timestamp = datetime.now(timezone.utc).isoformat()
    stats = []
    for field in contract.schema_spec.fields:
        if field.name not in df.columns:
            continue
        series = df[field.name]
        null_fraction = float(series.isna().mean())
        fs = FieldStats(
            run_id=run_id,
            contract_id=contract.contract_id,
            field_name=field.name,
            timestamp=timestamp,
            row_count=len(df),
            null_fraction=null_fraction,
        )
        if field.type in ("float", "integer"):
            numeric = series.dropna()
            if len(numeric) > 0:
                fs.mean = float(numeric.mean())
                fs.std = float(numeric.std()) if len(numeric) > 1 else 0.0
                fs.min_val = float(numeric.min())
                fs.max_val = float(numeric.max())
                fs.p25 = float(numeric.quantile(0.25))
                fs.p50 = float(numeric.quantile(0.50))
                fs.p75 = float(numeric.quantile(0.75))
                sample_size = min(500, len(numeric))
                fs.sample_values = (
                    numeric.sample(sample_size, random_state=42).astype(float).tolist()
                )
        elif field.type == "string":
            cat = series.dropna()
            if len(cat) > 0:
                vc = cat.astype(str).value_counts(normalize=True)
                fs.value_counts = {str(k): float(v) for k, v in vc.head(50).items()}
        stats.append(fs)
    return stats


class Validator:
    def __init__(
        self,
        contract: DataContract,
        obs_store: ObservationsStore | None = None,
        obs_db_path: str = "./observations.duckdb",
    ) -> None:
        self._contract = contract
        self._store = obs_store or ObservationsStore(db_path=obs_db_path)
        self._schema_plugins = [
            TypeValidator(), NullableValidator(), PatternValidator(),
            AllowedValuesValidator(), RangeValidator(),
            RowCountValidator(), FreshnessValidator(),
        ]
        self._stat_plugins = [
            KSTestValidator(), ChiSquaredValidator(), ZScoreValidator(),
            PSIValidator(), CompletenessValidator(),
        ]

    def validate(
        self, df: pd.DataFrame, batch_id: str | None = None
    ) -> ValidationResult:
        t0 = time.perf_counter()
        run_id = str(uuid4())
        batch_id = batch_id or str(uuid4())

        field_stats = _compute_field_stats(df, self._contract, run_id)
        baselines = {
            fs.field_name: self._store.get_baseline(
                self._contract.contract_id, fs.field_name
            )
            for fs in field_stats
        }

        violations: list[Violation] = []
        for plugin in self._schema_plugins:
            violations.extend(plugin.check(df, self._contract))
        for plugin in self._stat_plugins:
            violations.extend(plugin.check(df, self._contract, baselines))

        result = ValidationResult(
            run_id=run_id,
            contract_id=self._contract.contract_id,
            contract_version=self._contract.version,
            batch_id=batch_id,
            timestamp=datetime.now(timezone.utc),
            status=_derive_status(violations),
            row_count=len(df),
            duration_ms=(time.perf_counter() - t0) * 1000,
            violations=violations,
        )

        self._store.write_run(result)
        self._store.write_field_stats(run_id, self._contract.contract_id, field_stats)
        return result
