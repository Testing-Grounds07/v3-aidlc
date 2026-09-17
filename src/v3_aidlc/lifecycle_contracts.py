"""Load and validate governed V3-AIDLC route and mode contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


STAGES = {
    "discovery",
    "definition",
    "design",
    "implementation",
    "validation",
    "release",
    "operation",
    "retirement",
}
POSTURES = {"explore", "fast", "balanced", "assured", "emergency"}
REQUIREMENTS = {"required", "conditional", "optional"}
PREDICATE_KEYS = {"equals", "in"}


class ContractError(ValueError):
    """Raised when a lifecycle contract is invalid or incomplete."""


@dataclass(frozen=True)
class ModeSelection:
    mode_id: str
    requirement: str
    reason: str


@dataclass(frozen=True)
class SelectionResult:
    route_id: str
    route_version: str
    stage: str
    posture: str
    selected: tuple[ModeSelection, ...]
    inherited_controls: tuple[str, ...]


def load_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Cannot load contract {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Contract {path} must contain a JSON object")
    return value


def _require_string(contract: dict[str, Any], key: str) -> str:
    value = contract.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} must be a non-empty string")
    return value


def _validate_controls(controls: Any, field: str) -> tuple[str, ...]:
    if not isinstance(controls, list) or any(
        not isinstance(item, str) or not item for item in controls
    ):
        raise ContractError(f"{field} must be an array of stable control IDs")
    if len(controls) != len(set(controls)):
        raise ContractError(f"{field} contains duplicate control IDs")
    return tuple(controls)


def validate_mode_contract(contract: dict[str, Any]) -> None:
    _require_string(contract, "id")
    _require_string(contract, "version")
    _require_string(contract, "title")
    _require_string(contract, "objective")

    stages = contract.get("supportedStages")
    if not isinstance(stages, list) or not stages:
        raise ContractError("supportedStages must be a non-empty array")
    unknown_stages = set(stages) - STAGES
    if unknown_stages:
        raise ContractError(f"Unknown supported stages: {sorted(unknown_stages)}")
    if len(stages) != len(set(stages)):
        raise ContractError("supportedStages contains duplicates")

    roles = contract.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ContractError("roles must be a non-empty array")
    for role in roles:
        if not isinstance(role, dict):
            raise ContractError("Each role must be an object")
        _require_string(role, "name")
        _require_string(role, "responsibility")

    for field in ("requiredInputs", "requiredOutputs", "evidence", "completionCriteria"):
        value = contract.get(field)
        if not isinstance(value, list) or not value:
            raise ContractError(f"{field} must be a non-empty array")

    _validate_controls(contract.get("hardControls", []), "hardControls")

    budget = contract.get("attemptBudget")
    if not isinstance(budget, int) or budget < 1:
        raise ContractError("attemptBudget must be an integer of at least 1")

    profiles = contract.get("postureProfiles")
    if not isinstance(profiles, dict) or "balanced" not in profiles:
        raise ContractError("postureProfiles must define at least balanced")
    unknown_postures = set(profiles) - POSTURES
    if unknown_postures:
        raise ContractError(f"Unknown posture profiles: {sorted(unknown_postures)}")

    outcomes = contract.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        raise ContractError("outcomes must be a non-empty array")


def _validate_predicate(predicate: Any) -> None:
    if not isinstance(predicate, dict):
        raise ContractError("Each condition predicate must be an object")
    _require_string(predicate, "fact")
    operators = PREDICATE_KEYS.intersection(predicate)
    if len(operators) != 1:
        raise ContractError("Each predicate must use exactly one supported operator")
    unexpected = set(predicate) - {"fact"} - PREDICATE_KEYS
    if unexpected:
        raise ContractError(f"Unsupported predicate fields: {sorted(unexpected)}")
    if "in" in predicate and (
        not isinstance(predicate["in"], list) or not predicate["in"]
    ):
        raise ContractError("Predicate 'in' must contain a non-empty array")


def validate_route_contract(
    contract: dict[str, Any], mode_library: dict[str, dict[str, Any]]
) -> None:
    _require_string(contract, "id")
    _require_string(contract, "version")
    _require_string(contract, "title")
    _require_string(contract, "purpose")

    default_posture = contract.get("defaultPosture")
    allowed_postures = contract.get("allowedPostures")
    if default_posture not in POSTURES:
        raise ContractError(f"Unknown default posture: {default_posture}")
    if not isinstance(allowed_postures, list) or not allowed_postures:
        raise ContractError("allowedPostures must be a non-empty array")
    if set(allowed_postures) - POSTURES:
        raise ContractError("allowedPostures contains unknown values")
    if default_posture not in allowed_postures:
        raise ContractError("defaultPosture must be allowed")

    _validate_controls(contract.get("hardControls", []), "hardControls")

    stages = contract.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ContractError("stages must be a non-empty array")
    stage_ids = [stage.get("id") for stage in stages if isinstance(stage, dict)]
    if len(stage_ids) != len(stages) or set(stage_ids) - STAGES:
        raise ContractError("stages contains an invalid stage")
    if len(stage_ids) != len(set(stage_ids)):
        raise ContractError("stages contains duplicates")

    for stage in stages:
        rules = stage.get("modeRules")
        if not isinstance(rules, list) or not rules:
            raise ContractError(f"Stage {stage['id']} must define modeRules")
        seen_modes: set[str] = set()
        for rule in rules:
            if not isinstance(rule, dict):
                raise ContractError("Each mode rule must be an object")
            mode_id = _require_string(rule, "modeId")
            requirement = rule.get("requirement")
            if requirement not in REQUIREMENTS:
                raise ContractError(f"Unknown requirement for {mode_id}: {requirement}")
            if mode_id in seen_modes:
                raise ContractError(f"Duplicate mode rule for {mode_id}")
            seen_modes.add(mode_id)
            if mode_id not in mode_library:
                raise ContractError(f"Route references unknown mode: {mode_id}")
            validate_mode_contract(mode_library[mode_id])
            if stage["id"] not in mode_library[mode_id]["supportedStages"]:
                raise ContractError(
                    f"Mode {mode_id} does not support stage {stage['id']}"
                )
            conditions = rule.get("whenAll", [])
            if requirement == "conditional" and not conditions:
                raise ContractError(f"Conditional mode {mode_id} requires whenAll")
            if requirement != "conditional" and conditions:
                raise ContractError(
                    f"Only conditional mode {mode_id} may define whenAll"
                )
            for predicate in conditions:
                _validate_predicate(predicate)

    outcomes = contract.get("completionOutcomes")
    if not isinstance(outcomes, list) or not outcomes:
        raise ContractError("completionOutcomes must be a non-empty array")


def _matches(predicate: dict[str, Any], facts: dict[str, Any]) -> bool:
    if predicate["fact"] not in facts:
        return False
    actual = facts[predicate["fact"]]
    if "equals" in predicate:
        return actual == predicate["equals"]
    return actual in predicate["in"]


def select_modes(
    route: dict[str, Any],
    mode_library: dict[str, dict[str, Any]],
    stage: str,
    facts: dict[str, Any],
    posture: str | None = None,
    optional_mode_ids: Iterable[str] = (),
) -> SelectionResult:
    validate_route_contract(route, mode_library)
    selected_posture = posture or route["defaultPosture"]
    if selected_posture not in route["allowedPostures"]:
        raise ContractError(f"Posture {selected_posture} is not allowed by the route")

    stage_contract = next(
        (item for item in route["stages"] if item["id"] == stage), None
    )
    if stage_contract is None:
        raise ContractError(f"Route does not contain stage: {stage}")

    optional = set(optional_mode_ids)
    known_optional = {
        rule["modeId"]
        for rule in stage_contract["modeRules"]
        if rule["requirement"] == "optional"
    }
    unknown_optional = optional - known_optional
    if unknown_optional:
        raise ContractError(
            f"Modes are not optional for this stage: {sorted(unknown_optional)}"
        )

    selections: list[ModeSelection] = []
    for rule in stage_contract["modeRules"]:
        requirement = rule["requirement"]
        if requirement == "required":
            selections.append(
                ModeSelection(rule["modeId"], requirement, "required by route")
            )
        elif requirement == "conditional" and all(
            _matches(predicate, facts) for predicate in rule["whenAll"]
        ):
            matched = ", ".join(predicate["fact"] for predicate in rule["whenAll"])
            selections.append(
                ModeSelection(
                    rule["modeId"], requirement, f"matched authoritative facts: {matched}"
                )
            )
        elif requirement == "optional" and rule["modeId"] in optional:
            selections.append(
                ModeSelection(
                    rule["modeId"], requirement, "authorized optional selection"
                )
            )

    controls = set(route.get("hardControls", []))
    for selection in selections:
        controls.update(mode_library[selection.mode_id].get("hardControls", []))

    return SelectionResult(
        route_id=route["id"],
        route_version=route["version"],
        stage=stage,
        posture=selected_posture,
        selected=tuple(selections),
        inherited_controls=tuple(sorted(controls)),
    )


def load_mode_library(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    library: dict[str, dict[str, Any]] = {}
    for path in paths:
        contract = load_contract(path)
        validate_mode_contract(contract)
        mode_id = contract["id"]
        if mode_id in library:
            raise ContractError(f"Duplicate mode ID: {mode_id}")
        library[mode_id] = contract
    return library

