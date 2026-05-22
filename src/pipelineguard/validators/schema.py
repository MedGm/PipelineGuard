from __future__ import annotations
from datetime import datetime, timezone

import pandas as pd

from pipelineguard.contracts.models import DataContract
from pipelineguard.validators.base import Violation

_INT_DTYPES = {"int8", "int16", "int32", "int64", "Int8", "Int16", "Int32", "Int64",
               "uint8", "uint16", "uint32", "uint64"}
_FLOAT_DTYPES = _INT_DTYPES | {"float32", "float64", "Float32", "Float64"}
_STR_DTYPES = {"object", "string", "str"}
_BOOL_DTYPES = {"bool", "boolean"}

_TYPE_MAP: dict[str, set[str]] = {
    "string": _STR_DTYPES,
    "integer": _INT_DTYPES,
    "float": _FLOAT_DTYPES,
    "boolean": _BOOL_DTYPES,
    "timestamp": set(),  # handled via startswith("datetime64")
}


def _dtype_ok(dtype_str: str, field_type: str) -> bool:
    if field_type == "timestamp":
        return dtype_str.startswith("datetime64")
    return dtype_str in _TYPE_MAP.get(field_type, set())


class TypeValidator:
    name = "type_check"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines=None) -> list[Violation]:
        violations = []
        for field in contract.schema_spec.fields:
            if field.name not in df.columns:
                violations.append(Violation(
                    field=field.name, validator=self.name, severity="FAIL",
                    message=f"Field '{field.name}' not found in DataFrame",
                    suggestion=f"Add column '{field.name}' or update the contract",
                ))
                continue
            dtype_str = str(df[field.name].dtype)
            if not _dtype_ok(dtype_str, field.type):
                violations.append(Violation(
                    field=field.name, validator=self.name, severity="FAIL",
                    message=f"Field '{field.name}' dtype '{dtype_str}' incompatible with contract type '{field.type}'",
                    suggestion=f"Cast '{field.name}' to a {field.type}-compatible dtype",
                ))
        return violations


class NullableValidator:
    name = "nullable_check"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines=None) -> list[Violation]:
        completeness = contract.statistics.get("completeness", {})
        max_null_fraction = (
            completeness.get("max_null_fraction")
            if isinstance(completeness, dict) else None
        )
        violations = []
        for field in contract.schema_spec.fields:
            if field.name not in df.columns:
                continue
            null_count = int(df[field.name].isna().sum())
            null_fraction = null_count / len(df) if len(df) > 0 else 0.0
            if not field.nullable and null_count > 0:
                violations.append(Violation(
                    field=field.name, validator=self.name, severity="FAIL",
                    message=f"Field '{field.name}' is non-nullable but has {null_count} null(s)",
                    affected_rows=null_count,
                ))
            elif field.nullable and max_null_fraction is not None:
                if null_fraction > max_null_fraction:
                    violations.append(Violation(
                        field=field.name, validator=self.name, severity="FAIL",
                        message=(f"Field '{field.name}' null fraction {null_fraction:.3f} "
                                 f"exceeds max {max_null_fraction}"),
                        metric=null_fraction, threshold=max_null_fraction,
                    ))
        return violations


class PatternValidator:
    name = "pattern_check"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines=None) -> list[Violation]:
        violations = []
        for field in contract.schema_spec.fields:
            if field.pattern is None or field.name not in df.columns:
                continue
            series = df[field.name].dropna().astype(str)
            mismatches = int((~series.str.match(field.pattern)).sum())
            if mismatches > 0:
                violations.append(Violation(
                    field=field.name, validator=self.name, severity="FAIL",
                    message=f"Field '{field.name}': {mismatches} value(s) don't match pattern '{field.pattern}'",
                    affected_rows=mismatches,
                    suggestion="Check upstream data or update pattern in contract",
                ))
        return violations


class AllowedValuesValidator:
    name = "allowed_values_check"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines=None) -> list[Violation]:
        violations = []
        for field in contract.schema_spec.fields:
            if field.allowed_values is None or field.name not in df.columns:
                continue
            allowed = set(field.allowed_values)
            actual = set(df[field.name].dropna().astype(str).unique())
            unexpected = actual - allowed
            if unexpected:
                count = int(df[field.name].isin(unexpected).sum())
                violations.append(Violation(
                    field=field.name, validator=self.name, severity="FAIL",
                    message=f"Field '{field.name}' has unexpected values: {sorted(unexpected)!r}",
                    affected_rows=count,
                    suggestion=f"Add {sorted(unexpected)!r} to contract allowed_values or fix upstream",
                ))
        return violations


class RangeValidator:
    name = "range_check"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines=None) -> list[Violation]:
        violations = []
        for field in contract.schema_spec.fields:
            if field.min is None and field.max is None:
                continue
            if field.name not in df.columns:
                continue
            series = df[field.name].dropna()
            count = 0
            parts = []
            if field.min is not None:
                below = int((series < field.min).sum())
                if below:
                    count += below
                    parts.append(f"{below} below min ({field.min})")
            if field.max is not None:
                above = int((series > field.max).sum())
                if above:
                    count += above
                    parts.append(f"{above} above max ({field.max})")
            if count > 0:
                violations.append(Violation(
                    field=field.name, validator=self.name, severity="FAIL",
                    message=f"Field '{field.name}': {', '.join(parts)}",
                    affected_rows=count,
                    suggestion="Update contract range bounds or fix upstream data",
                ))
        return violations


class RowCountValidator:
    name = "row_count_check"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines=None) -> list[Violation]:
        completeness = contract.statistics.get("completeness", {})
        if not isinstance(completeness, dict):
            return []
        min_row_count = completeness.get("min_row_count")
        if min_row_count is None:
            return []
        if len(df) < min_row_count:
            return [Violation(
                field=None, validator=self.name, severity="FAIL",
                message=f"Batch has {len(df)} rows, expected at least {min_row_count}",
                metric=float(len(df)), threshold=float(min_row_count),
                suggestion="Check if upstream pipeline is truncating results",
            )]
        return []


class FreshnessValidator:
    name = "freshness_check"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines=None) -> list[Violation]:
        if contract.freshness is None:
            return []
        ts_fields = [f for f in contract.schema_spec.fields if f.type == "timestamp"]
        if not ts_fields:
            return []
        ts_col = ts_fields[0].name
        if ts_col not in df.columns:
            return []
        latest = df[ts_col].max()
        if hasattr(latest, "to_pydatetime"):
            latest = latest.to_pydatetime()
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        delay_minutes = (datetime.now(timezone.utc) - latest).total_seconds() / 60
        max_delay = contract.freshness.max_delay_minutes
        if delay_minutes > max_delay:
            return [Violation(
                field=ts_col, validator=self.name, severity="WARN",
                message=f"Latest record is {delay_minutes:.1f} min old (max: {max_delay} min)",
                metric=delay_minutes, threshold=float(max_delay),
                suggestion="Check if data pipeline is running on schedule",
            )]
        return []
