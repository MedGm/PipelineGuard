from __future__ import annotations

import numpy as np
from scipy import stats as scipy_stats

import pandas as pd

from pipelineguard.contracts.models import DataContract
from pipelineguard.validators.base import FieldStats, Violation

_KS_ALPHA = {"low": 0.001, "medium": 0.05, "high": 0.10}
_PSI_WARN = {"low": 0.25, "medium": 0.10, "high": 0.05}


def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    bin_edges = np.percentile(expected, np.linspace(0, 100, buckets + 1))
    bin_edges[0] -= 1e-6
    bin_edges[-1] += 1e-6
    e_counts, _ = np.histogram(expected, bins=bin_edges)
    a_counts, _ = np.histogram(actual, bins=bin_edges)
    e_pct = np.clip(e_counts / len(expected), 1e-10, None)
    a_pct = np.clip(a_counts / len(actual), 1e-10, None)
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))


def _sensitivity(contract: DataContract, field_name: str) -> str:
    field_stats = contract.statistics.get(field_name, {})
    if isinstance(field_stats, dict):
        return field_stats.get("drift_sensitivity", "medium")
    return "medium"


def _numeric_fields(contract: DataContract) -> list[str]:
    return [f.name for f in contract.schema_spec.fields if f.type in ("float", "integer")]


def _string_fields(contract: DataContract) -> list[str]:
    return [f.name for f in contract.schema_spec.fields if f.type == "string"]


class KSTestValidator:
    name = "ks_test"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines: dict | None = None) -> list[Violation]:
        if baselines is None:
            return []
        violations = []
        for field_name in _numeric_fields(contract):
            field_cfg = contract.statistics.get(field_name, {})
            if not isinstance(field_cfg, dict) or "drift_sensitivity" not in field_cfg:
                continue
            baseline = baselines.get(field_name)
            if baseline is None or baseline.sample_values is None:
                continue
            if field_name not in df.columns:
                continue
            current = df[field_name].dropna().values
            reference = np.array(baseline.sample_values)
            if len(current) < 5 or len(reference) < 5:
                continue
            alpha = _KS_ALPHA.get(_sensitivity(contract, field_name), 0.05)
            stat, p_value = scipy_stats.ks_2samp(reference, current)
            if p_value < alpha:
                violations.append(Violation(
                    field=field_name, validator=self.name, severity="WARN",
                    message=(f"Distribution shift in '{field_name}': "
                             f"KS={stat:.3f}, p={p_value:.4f} (alpha={alpha})"),
                    metric=p_value, threshold=alpha,
                    suggestion=f"Run `pg tune --contract {contract.contract_id} --field {field_name}`",
                ))
        return violations


class PSIValidator:
    name = "psi_check"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines: dict | None = None) -> list[Violation]:
        if baselines is None:
            return []
        violations = []
        for field_name in _numeric_fields(contract):
            field_cfg = contract.statistics.get(field_name, {})
            if not isinstance(field_cfg, dict) or "drift_sensitivity" not in field_cfg:
                continue
            baseline = baselines.get(field_name)
            if baseline is None or baseline.sample_values is None:
                continue
            if field_name not in df.columns:
                continue
            current = df[field_name].dropna().values
            reference = np.array(baseline.sample_values)
            if len(current) < 5 or len(reference) < 5:
                continue
            sensitivity = _sensitivity(contract, field_name)
            warn_threshold = _PSI_WARN.get(sensitivity, 0.10)
            score = _psi(reference, current)
            if score > 0.20:
                severity = "FAIL"
            elif score > warn_threshold:
                severity = "WARN"
            else:
                continue
            violations.append(Violation(
                field=field_name, validator=self.name, severity=severity,
                message=f"PSI={score:.3f} for '{field_name}' (warn>{warn_threshold}, fail>0.20)",
                metric=score, threshold=warn_threshold,
                suggestion="Significant distribution shift. Consider retraining if PSI > 0.20.",
            ))
        return violations


class ZScoreValidator:
    name = "z_score_check"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines: dict | None = None) -> list[Violation]:
        if baselines is None:
            return []
        violations = []
        for field_name in _numeric_fields(contract):
            field_cfg = contract.statistics.get(field_name, {})
            if not isinstance(field_cfg, dict):
                continue
            outlier_zscore = field_cfg.get("outlier_zscore")
            if outlier_zscore is None:
                continue
            baseline = baselines.get(field_name)
            if baseline is None or baseline.mean is None or baseline.std is None:
                continue
            if field_name not in df.columns or baseline.std == 0:
                continue
            series = df[field_name].dropna().values
            z_scores = np.abs((series - baseline.mean) / baseline.std)
            outlier_count = int((z_scores > outlier_zscore).sum())
            if outlier_count > 0:
                violations.append(Violation(
                    field=field_name, validator=self.name, severity="WARN",
                    message=f"Field '{field_name}': {outlier_count} value(s) exceed z-score {outlier_zscore}",
                    affected_rows=outlier_count,
                    metric=float(z_scores.max()), threshold=float(outlier_zscore),
                    suggestion="Investigate outliers or widen outlier_zscore in contract",
                ))
        return violations


class ChiSquaredValidator:
    name = "chi_squared_test"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines: dict | None = None) -> list[Violation]:
        if baselines is None:
            return []
        violations = []
        for field_name in _string_fields(contract):
            field_cfg = contract.statistics.get(field_name, {})
            if not isinstance(field_cfg, dict) or "drift_sensitivity" not in field_cfg:
                continue
            baseline = baselines.get(field_name)
            if baseline is None or baseline.value_counts is None:
                continue
            if field_name not in df.columns:
                continue
            n = int(df[field_name].dropna().shape[0])
            if n == 0:
                continue
            alpha = _KS_ALPHA.get(_sensitivity(contract, field_name), 0.05)
            current_vc = df[field_name].dropna().astype(str).value_counts(normalize=True)
            categories = list(baseline.value_counts.keys())
            ref_fracs = np.array([baseline.value_counts[c] for c in categories])
            cur_fracs = np.array([current_vc.get(c, 0.0) for c in categories])
            expected = ref_fracs * n
            if (expected < 5).any():
                continue
            observed = cur_fracs * n
            _, p_value = scipy_stats.chisquare(observed, expected)
            if p_value < alpha:
                violations.append(Violation(
                    field=field_name, validator=self.name, severity="WARN",
                    message=f"Categorical shift in '{field_name}': p={p_value:.4f} (alpha={alpha})",
                    metric=p_value, threshold=alpha,
                    suggestion="Category proportions have shifted. Investigate upstream.",
                ))
        return violations


class CompletenessValidator:
    name = "completeness_drift"

    def check(self, df: pd.DataFrame, contract: DataContract,
              baselines: dict | None = None) -> list[Violation]:
        if baselines is None:
            return []
        violations = []
        for field in contract.schema_spec.fields:
            baseline = baselines.get(field.name)
            if baseline is None or field.name not in df.columns:
                continue
            current_nf = float(df[field.name].isna().mean())
            increase = current_nf - baseline.null_fraction
            if increase > 0.05:
                violations.append(Violation(
                    field=field.name, validator=self.name, severity="WARN",
                    message=(f"Null fraction for '{field.name}' increased from "
                             f"{baseline.null_fraction:.3f} to {current_nf:.3f} (+{increase:.3f})"),
                    metric=current_nf, threshold=baseline.null_fraction + 0.05,
                    suggestion="Investigate upstream for missing value increase",
                ))
        return violations
