from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipelineguard.contracts.models import DataContract, ContractDiff


def parse_version(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected MAJOR.MINOR.PATCH, got {v!r}")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def latest_version(versions: list[str]) -> str:
    if not versions:
        raise ValueError("versions list must not be empty")
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
                field_name=name,
                change_type="removed",
                detail=f"field '{name}' removed",
            ))
        elif new_fields[name].type != field.type:
            breaking.append(BreakingChange(
                field_name=name,
                change_type="type_changed",
                detail=(
                    f"field '{name}' type changed from "
                    f"{field.type!r} to {new_fields[name].type!r}"
                ),
            ))
        # Note: nullable, min, max, pattern, allowed_values changes are not
        # classified as breaking in Phase 0. Phase 1 validators will enforce these.

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
