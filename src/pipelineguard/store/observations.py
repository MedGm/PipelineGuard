from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from pydantic import BaseModel

from pipelineguard.validators.base import FieldStats, ValidationResult, Violation


class RunSummary(BaseModel):
    run_id: str
    contract_id: str
    timestamp: str
    status: str
    row_count: int
    violation_count: int


_TABLES = [
    """CREATE TABLE IF NOT EXISTS validation_runs (
        run_id           TEXT PRIMARY KEY,
        contract_id      TEXT NOT NULL,
        contract_version TEXT NOT NULL,
        batch_id         TEXT NOT NULL,
        timestamp        TEXT NOT NULL,
        status           TEXT NOT NULL,
        row_count        INTEGER NOT NULL,
        duration_ms      REAL NOT NULL,
        violation_count  INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS violations (
        run_id        TEXT NOT NULL,
        field         TEXT,
        validator     TEXT NOT NULL,
        severity      TEXT NOT NULL,
        message       TEXT NOT NULL,
        affected_rows INTEGER,
        metric        REAL,
        threshold     REAL,
        suggestion    TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS field_stats (
        run_id            TEXT NOT NULL,
        contract_id       TEXT NOT NULL,
        field_name        TEXT NOT NULL,
        timestamp         TEXT NOT NULL,
        row_count         INTEGER NOT NULL,
        null_fraction     REAL NOT NULL,
        mean              REAL,
        std               REAL,
        min_val           REAL,
        max_val           REAL,
        p25               REAL,
        p50               REAL,
        p75               REAL,
        value_counts      TEXT,
        sample_values     TEXT
    )""",
]


class ObservationsStore:
    def __init__(self, db_path: str = "./observations.duckdb") -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            for ddl in _TABLES:
                conn.execute(ddl)
        finally:
            conn.close()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(database=self._db_path)

    def write_run(self, result: ValidationResult) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO validation_runs
                   (run_id, contract_id, contract_version, batch_id, timestamp,
                    status, row_count, duration_ms, violation_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [result.run_id, result.contract_id, result.contract_version,
                 result.batch_id, result.timestamp.isoformat(), result.status,
                 result.row_count, result.duration_ms, len(result.violations)],
            )
            for v in result.violations:
                conn.execute(
                    """INSERT INTO violations
                       (run_id, field, validator, severity, message,
                        affected_rows, metric, threshold, suggestion)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [result.run_id, v.field, v.validator, v.severity,
                     v.message, v.affected_rows, v.metric, v.threshold, v.suggestion],
                )
        finally:
            conn.close()

    def write_field_stats(
        self, run_id: str, contract_id: str, stats: list[FieldStats]
    ) -> None:
        conn = self._connect()
        try:
            for s in stats:
                conn.execute(
                    """INSERT INTO field_stats
                       (run_id, contract_id, field_name, timestamp, row_count,
                        null_fraction, mean, std, min_val, max_val,
                        p25, p50, p75, value_counts, sample_values)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [run_id, contract_id, s.field_name, s.timestamp,
                     s.row_count, s.null_fraction, s.mean, s.std,
                     s.min_val, s.max_val, s.p25, s.p50, s.p75,
                     json.dumps(s.value_counts) if s.value_counts else None,
                     json.dumps(s.sample_values) if s.sample_values else None],
                )
        finally:
            conn.close()

    def get_baseline(self, contract_id: str, field_name: str) -> FieldStats | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT run_id, contract_id, field_name, timestamp, row_count,
                          null_fraction, mean, std, min_val, max_val,
                          p25, p50, p75, value_counts, sample_values
                   FROM field_stats
                   WHERE contract_id = ? AND field_name = ?
                   ORDER BY timestamp DESC LIMIT 1""",
                [contract_id, field_name],
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return FieldStats(
            run_id=row[0], contract_id=row[1], field_name=row[2],
            timestamp=row[3], row_count=row[4], null_fraction=row[5],
            mean=row[6], std=row[7], min_val=row[8], max_val=row[9],
            p25=row[10], p50=row[11], p75=row[12],
            value_counts=json.loads(row[13]) if row[13] else None,
            sample_values=json.loads(row[14]) if row[14] else None,
        )

    def get_run(self, run_id: str) -> ValidationResult | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT run_id, contract_id, contract_version, batch_id,
                          timestamp, status, row_count, duration_ms
                   FROM validation_runs WHERE run_id = ?""",
                [run_id],
            ).fetchone()
            if row is None:
                return None
            vrows = conn.execute(
                """SELECT field, validator, severity, message,
                          affected_rows, metric, threshold, suggestion
                   FROM violations WHERE run_id = ?""",
                [run_id],
            ).fetchall()
        finally:
            conn.close()
        violations = [
            Violation(
                field=vr[0], validator=vr[1], severity=vr[2],
                message=vr[3], affected_rows=vr[4],
                metric=vr[5], threshold=vr[6], suggestion=vr[7],
            )
            for vr in vrows
        ]
        return ValidationResult(
            run_id=row[0], contract_id=row[1], contract_version=row[2],
            batch_id=row[3], timestamp=datetime.fromisoformat(row[4]),
            status=row[5], row_count=row[6], duration_ms=row[7],
            violations=violations,
        )

    def list_runs(self, contract_id: str, limit: int = 20) -> list[RunSummary]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT run_id, contract_id, timestamp, status, row_count, violation_count
                   FROM validation_runs WHERE contract_id = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                [contract_id, limit],
            ).fetchall()
        finally:
            conn.close()
        return [
            RunSummary(
                run_id=r[0], contract_id=r[1], timestamp=r[2],
                status=r[3], row_count=r[4], violation_count=r[5],
            )
            for r in rows
        ]
