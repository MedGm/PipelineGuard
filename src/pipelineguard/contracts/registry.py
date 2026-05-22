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
