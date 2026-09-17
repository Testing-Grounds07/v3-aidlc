"""Deterministic minimum-context assembly and disclosure control."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


KINDS = {
    "instruction",
    "objective",
    "requirement",
    "constraint",
    "decision",
    "architecture",
    "artifact_reference",
    "evidence_reference",
    "finding",
    "learning",
    "conversation_excerpt",
    "tool_contract",
    "secret_reference",
    "external_fact",
    "assumption",
}
SOURCES = {
    "organization_policy",
    "project_policy",
    "user_instruction",
    "canonical_state",
    "governed_contract",
    "verified_evidence",
    "external_source",
    "liaison_summary",
    "assumption",
}
SOURCE_AUTHORITY = {
    "organization_policy": 100,
    "project_policy": 95,
    "user_instruction": 90,
    "canonical_state": 85,
    "governed_contract": 80,
    "verified_evidence": 70,
    "external_source": 40,
    "liaison_summary": 20,
    "assumption": 10,
}
SENSITIVITIES = {"public", "internal", "confidential", "restricted", "secret"}
SENSITIVITY_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
    "secret": 4,
}
INTEGRITY = {"authoritative", "verified", "unverified", "assumption"}
EXPLICIT_GRANT_LEVELS = {"confidential", "restricted", "secret"}
DISCLOSURE_AUTHORITIES = {"organization_policy", "project_policy", "user_decision"}


class ContextError(ValueError):
    """Raised when context cannot be compiled safely and deterministically."""


@dataclass(frozen=True)
class Exclusion:
    item_id: str
    reason: str


@dataclass(frozen=True)
class ContextManifest:
    manifest_id: str
    run_id: str
    role: str
    recipe_id: str
    recipe_version: str
    generated_at: str
    selected_items: tuple[dict[str, Any], ...]
    exclusions: tuple[Exclusion, ...]
    tool_allowlist: tuple[str, ...]
    network_allowlist: tuple[str, ...]
    total_bytes: int
    sha256: str


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContextError(f"Cannot load {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContextError(f"{label} {path} must contain a JSON object")
    return value


def load_contract(path: Path) -> dict[str, Any]:
    return _load_json(path, "contract")


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ContextError(f"{key} must be a non-empty string")
    return result


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ContextError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ContextError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _string_array(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ContextError(f"{field} must be a string array")
    if len(value) != len(set(value)):
        raise ContextError(f"{field} contains duplicates")
    return tuple(value)


def validate_context_item(item: dict[str, Any]) -> None:
    for key in (
        "id",
        "revision",
        "kind",
        "sourceType",
        "sourceRef",
        "sensitivity",
        "integrity",
        "projectId",
        "createdAt",
        "claimKey",
    ):
        _required_string(item, key)
    if item["kind"] not in KINDS:
        raise ContextError(f"Unknown context kind: {item['kind']}")
    if item["sourceType"] not in SOURCES:
        raise ContextError(f"Unknown source type: {item['sourceType']}")
    if item["sensitivity"] not in SENSITIVITIES:
        raise ContextError(f"Unknown sensitivity: {item['sensitivity']}")
    if item["integrity"] not in INTEGRITY:
        raise ContextError(f"Unknown integrity: {item['integrity']}")
    if item["sourceType"] in {"external_source", "liaison_summary"} and item[
        "integrity"
    ] == "authoritative":
        raise ContextError(f"{item['sourceType']} cannot be authoritative")
    if item["sourceType"] == "assumption" and (
        item["integrity"] != "assumption" or item["kind"] != "assumption"
    ):
        raise ContextError("Assumption sources must be labeled as assumptions")
    if item["kind"] == "assumption" and item["integrity"] != "assumption":
        raise ContextError("Assumption items must use assumption integrity")
    _parse_time(item["createdAt"], "createdAt")
    for field in ("entityIds", "stages", "modes", "roles", "relevanceTags"):
        _string_array(item.get(field, []), field)
    if not isinstance(item.get("alwaysInclude"), bool):
        raise ContextError("alwaysInclude must be boolean")
    if item["kind"] == "secret_reference":
        _required_string(item, "reference")
        if "content" in item:
            raise ContextError("Secret references cannot contain secret content")
        if item["sensitivity"] != "secret":
            raise ContextError("Secret references must use secret sensitivity")
    else:
        _required_string(item, "content")
        if "reference" in item:
            raise ContextError("Only secret_reference items may contain reference")
        if item["sensitivity"] == "secret":
            raise ContextError("Secret values must be represented as references")
    expires_at = item.get("expiresAt")
    if expires_at is not None:
        _parse_time(expires_at, "expiresAt")


def validate_recipe(recipe: dict[str, Any]) -> None:
    for key in ("id", "version", "title", "role"):
        _required_string(recipe, key)
    allowed = _string_array(recipe.get("allowedKinds"), "allowedKinds")
    required = _string_array(recipe.get("requiredKinds"), "requiredKinds")
    if set(allowed) - KINDS or set(required) - KINDS:
        raise ContextError("Recipe contains unknown context kinds")
    if set(required) - set(allowed):
        raise ContextError("requiredKinds must also be allowed")
    sources = _string_array(recipe.get("allowedSources"), "allowedSources")
    if set(sources) - SOURCES:
        raise ContextError("Recipe contains unknown source types")
    if recipe.get("maxSensitivity") not in SENSITIVITIES:
        raise ContextError("Recipe maxSensitivity is invalid")
    for key in ("maxItems", "maxBytes"):
        if not isinstance(recipe.get(key), int) or recipe[key] < 1:
            raise ContextError(f"{key} must be a positive integer")
    priority = _string_array(recipe.get("kindPriority"), "kindPriority")
    if set(priority) != set(allowed):
        raise ContextError("kindPriority must list every allowed kind exactly once")
    _string_array(recipe.get("toolAllowlist", []), "toolAllowlist")
    _string_array(recipe.get("networkAllowlist", []), "networkAllowlist")


def validate_disclosure_grant(grant: dict[str, Any]) -> None:
    for key in (
        "id",
        "projectId",
        "recipientRole",
        "purpose",
        "grantedBy",
        "authority",
        "expiresAt",
    ):
        _required_string(grant, key)
    item_ids = _string_array(grant.get("itemIds"), "itemIds")
    if not item_ids:
        raise ContextError("Disclosure grants must name at least one exact item")
    run_ids = _string_array(grant.get("runIds"), "runIds")
    if not run_ids:
        raise ContextError("Disclosure grants must name at least one exact run")
    if grant["authority"] not in DISCLOSURE_AUTHORITIES:
        raise ContextError("Disclosure grant authority is not accepted")
    _parse_time(grant["expiresAt"], "expiresAt")


def _scope_matches(item: dict[str, Any], run: dict[str, Any]) -> bool:
    if item["projectId"] != run["projectId"]:
        return False
    dimensions = (
        ("entityIds", set(run.get("entityIds", []))),
        ("stages", {run.get("stage")}),
        ("modes", set(run.get("modes", []))),
        ("roles", {run["role"]}),
    )
    for field, active in dimensions:
        declared = set(item.get(field, []))
        if declared and not declared.intersection(active):
            return False
    return True


def _has_grant(
    item: dict[str, Any], run: dict[str, Any], grants: Iterable[dict[str, Any]], now: datetime
) -> bool:
    for grant in grants:
        validate_disclosure_grant(grant)
        if (
            grant["projectId"] == run["projectId"]
            and grant["recipientRole"] == run["role"]
            and run["runId"] in grant["runIds"]
            and item["id"] in grant["itemIds"]
            and now <= _parse_time(grant["expiresAt"], "expiresAt")
        ):
            return True
    return False


def _item_payload(item: dict[str, Any]) -> str:
    return item.get("content", item.get("reference", ""))


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compile_context(
    recipe: dict[str, Any],
    run: dict[str, Any],
    candidates: Iterable[dict[str, Any]],
    grants: Iterable[dict[str, Any]],
    generated_at: str,
) -> ContextManifest:
    validate_recipe(recipe)
    for key in ("runId", "projectId", "role"):
        _required_string(run, key)
    _string_array(run.get("entityIds", []), "run.entityIds")
    _string_array(run.get("modes", []), "run.modes")
    task_tags_tuple = _string_array(run.get("taskTags", []), "run.taskTags")
    if not task_tags_tuple:
        raise ContextError("run.taskTags must contain at least one bounded task tag")
    if run["role"] != recipe["role"]:
        raise ContextError("Run role does not match the context recipe")
    now = _parse_time(generated_at, "generatedAt")
    task_tags = set(run.get("taskTags", []))
    kind_priority = {kind: index for index, kind in enumerate(recipe["kindPriority"])}
    grants = tuple(grants)
    for grant in grants:
        validate_disclosure_grant(grant)
    exclusions: list[Exclusion] = []
    eligible: list[dict[str, Any]] = []

    seen_ids: set[str] = set()
    for item in candidates:
        validate_context_item(item)
        if item["id"] in seen_ids:
            raise ContextError(f"Duplicate context item ID: {item['id']}")
        seen_ids.add(item["id"])
        if item["kind"] not in recipe["allowedKinds"]:
            exclusions.append(Exclusion(item["id"], "kind not allowed by recipe"))
            continue
        if item["sourceType"] not in recipe["allowedSources"]:
            exclusions.append(Exclusion(item["id"], "source not allowed by recipe"))
            continue
        if SENSITIVITY_RANK[item["sensitivity"]] > SENSITIVITY_RANK[
            recipe["maxSensitivity"]
        ]:
            exclusions.append(Exclusion(item["id"], "sensitivity exceeds recipe"))
            continue
        if not _scope_matches(item, run):
            exclusions.append(Exclusion(item["id"], "outside run scope"))
            continue
        if item.get("expiresAt") and now > _parse_time(item["expiresAt"], "expiresAt"):
            exclusions.append(Exclusion(item["id"], "context item expired"))
            continue
        if item["sensitivity"] in EXPLICIT_GRANT_LEVELS and not _has_grant(
            item, run, grants, now
        ):
            exclusions.append(Exclusion(item["id"], "exact disclosure grant missing"))
            continue
        tags = set(item.get("relevanceTags", []))
        if not item["alwaysInclude"] and task_tags and not tags.intersection(task_tags):
            exclusions.append(Exclusion(item["id"], "not relevant to run task tags"))
            continue
        eligible.append(item)

    by_claim: dict[str, list[dict[str, Any]]] = {}
    for item in eligible:
        by_claim.setdefault(item["claimKey"], []).append(item)
    resolved: list[dict[str, Any]] = []
    for claim_key, items in by_claim.items():
        highest = max(SOURCE_AUTHORITY[item["sourceType"]] for item in items)
        leaders = [
            item for item in items if SOURCE_AUTHORITY[item["sourceType"]] == highest
        ]
        values = {_item_payload(item) for item in leaders}
        if len(values) > 1:
            raise ContextError(
                f"Equal-authority conflict requires reconciliation: {claim_key}"
            )
        leaders.sort(key=lambda item: (item["createdAt"], item["id"]), reverse=True)
        winner = leaders[0]
        resolved.append(winner)
        for item in items:
            if item["id"] != winner["id"]:
                exclusions.append(
                    Exclusion(item["id"], f"superseded by higher-precedence {winner['id']}")
                )

    resolved.sort(
        key=lambda item: (
            0 if item["alwaysInclude"] else 1,
            -SOURCE_AUTHORITY[item["sourceType"]],
            kind_priority[item["kind"]],
            item["id"],
        )
    )
    selected: list[dict[str, Any]] = []
    total_bytes = 0
    for item in resolved:
        rendered = {
            "id": item["id"],
            "revision": item["revision"],
            "kind": item["kind"],
            "sourceType": item["sourceType"],
            "sourceRef": item["sourceRef"],
            "sensitivity": item["sensitivity"],
            "integrity": item["integrity"],
            "claimKey": item["claimKey"],
            "content": item.get("content"),
            "reference": item.get("reference"),
        }
        item_bytes = len(
            json.dumps(rendered, sort_keys=True, ensure_ascii=False).encode("utf-8")
        )
        if len(selected) >= recipe["maxItems"] or total_bytes + item_bytes > recipe[
            "maxBytes"
        ]:
            exclusions.append(Exclusion(item["id"], "context budget exhausted"))
            continue
        selected.append(rendered)
        total_bytes += item_bytes

    selected_kinds = {item["kind"] for item in selected}
    missing = set(recipe["requiredKinds"]) - selected_kinds
    if missing:
        raise ContextError(f"Required context kinds are unavailable: {sorted(missing)}")

    manifest_body = {
        "runId": run["runId"],
        "role": run["role"],
        "recipeId": recipe["id"],
        "recipeVersion": recipe["version"],
        "generatedAt": generated_at,
        "selectedItems": selected,
        "toolAllowlist": recipe.get("toolAllowlist", []),
        "networkAllowlist": recipe.get("networkAllowlist", []),
        "totalBytes": total_bytes,
    }
    digest = _canonical_digest(manifest_body)
    return ContextManifest(
        manifest_id=f"CTX-{run['runId']}-{digest[:12]}",
        run_id=run["runId"],
        role=run["role"],
        recipe_id=recipe["id"],
        recipe_version=recipe["version"],
        generated_at=generated_at,
        selected_items=tuple(selected),
        exclusions=tuple(sorted(exclusions, key=lambda item: item.item_id)),
        tool_allowlist=tuple(recipe.get("toolAllowlist", [])),
        network_allowlist=tuple(recipe.get("networkAllowlist", [])),
        total_bytes=total_bytes,
        sha256=digest,
    )
