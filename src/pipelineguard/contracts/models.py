from __future__ import annotations
import re
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["string", "integer", "float", "boolean", "timestamp"]
    nullable: bool = True
    pattern: Optional[str] = None
    allowed_values: Optional[list[str]] = None
    min: Optional[float] = None
    max: Optional[float] = None


class SchemaSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[FieldSpec]


class FreshnessSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_delay_minutes: int


class RemediationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

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
    field_name: str
    change_type: Literal["removed", "type_changed"]  # "renamed" deferred to Phase 1
    detail: str


class ContractDiff(BaseModel):
    contract_id: str
    from_version: str
    to_version: str
    breaking_changes: list[BreakingChange]
    minor_changes: list[str]
