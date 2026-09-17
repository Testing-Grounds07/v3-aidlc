"""Deterministic conflict-aware scheduling and integration contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable


class SchedulerError(ValueError):
    """Raised when scheduling or integration input is unsafe or inconsistent."""


class ClaimAccess(StrEnum):
    READ = "read"
    WRITE = "write"
    EXCLUSIVE = "exclusive"


class ScheduleDecision(StrEnum):
    SELECTED = "selected"
    DEFERRED = "deferred"


PRIORITY_CLASS = {
    "safety_recovery": 0,
    "critical_path": 1,
    "user_priority": 2,
    "integration_blocker": 3,
    "intent_value": 4,
    "uncertainty_reduction": 5,
    "normal": 6,
}
TERMINAL_INTEGRATION = {"passed", "failed", "inconclusive"}


@dataclass(frozen=True)
class ScheduleEntry:
    work_package_id: str
    decision: ScheduleDecision
    reasons: tuple[str, ...]
    effective_priority: int


@dataclass(frozen=True)
class SchedulePlan:
    generated_at: str
    state_revision: str
    entries: tuple[ScheduleEntry, ...]
    selected_work_packages: tuple[str, ...]


def schedule_plan_to_dict(plan: SchedulePlan) -> dict[str, Any]:
    return {
        "schemaVersion": "0.1",
        "generatedAt": plan.generated_at,
        "stateRevision": plan.state_revision,
        "entries": [
            {
                "workPackageId": item.work_package_id,
                "decision": item.decision.value,
                "reasons": list(item.reasons),
                "effectivePriority": item.effective_priority,
            }
            for item in plan.entries
        ],
        "selectedWorkPackageIds": list(plan.selected_work_packages),
    }


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise SchedulerError(f"{key} must be a non-empty string")
    return result


def _strings(value: Any, key: str, *, minimum: int = 0) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise SchedulerError(f"{key} must be a string array")
    if len(value) < minimum:
        raise SchedulerError(f"{key} must contain at least {minimum} item(s)")
    if len(value) != len(set(value)):
        raise SchedulerError(f"{key} contains duplicates")
    return tuple(value)


def _parse_time(value: Any, key: str) -> datetime:
    if not isinstance(value, str):
        raise SchedulerError(f"{key} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SchedulerError(f"{key} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise SchedulerError(f"{key} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _nonnegative_int(value: Any, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SchedulerError(f"{key} must be a non-negative integer")
    return value


def validate_claim(claim: dict[str, Any]) -> None:
    _required_string(claim, "domain")
    try:
        ClaimAccess(claim.get("access"))
    except ValueError as error:
        raise SchedulerError("claim access must be read, write, or exclusive") from error


def claims_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    validate_claim(left)
    validate_claim(right)
    if left["domain"] != right["domain"]:
        return False
    return left["access"] != ClaimAccess.READ or right["access"] != ClaimAccess.READ


def validate_candidate(candidate: dict[str, Any]) -> None:
    for key in (
        "schemaVersion",
        "projectId",
        "workPackageId",
        "subjectRevision",
        "workstreamId",
        "adapterId",
        "role",
        "priorityClass",
        "queuedAt",
    ):
        _required_string(candidate, key)
    if candidate["priorityClass"] not in PRIORITY_CLASS:
        raise SchedulerError("priorityClass is invalid")
    user_priority = candidate.get("userPriority")
    if not isinstance(user_priority, int) or isinstance(user_priority, bool):
        raise SchedulerError("userPriority must be an integer")
    _parse_time(candidate["queuedAt"], "queuedAt")
    _strings(candidate.get("dependencyIds"), "dependencyIds")
    claims = candidate.get("claims")
    if not isinstance(claims, list) or not claims:
        raise SchedulerError("claims must be a non-empty array")
    seen_domains: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            raise SchedulerError("each claim must be an object")
        validate_claim(claim)
        if claim["domain"] in seen_domains:
            raise SchedulerError("candidate contains duplicate conflict domains")
        seen_domains.add(claim["domain"])
    costs = candidate.get("quotaCosts")
    if not isinstance(costs, dict) or not costs:
        raise SchedulerError("quotaCosts must be a non-empty object")
    for dimension, amount in costs.items():
        if not isinstance(dimension, str) or not dimension:
            raise SchedulerError("quota dimension must be a non-empty string")
        _nonnegative_int(amount, f"quotaCosts.{dimension}")


def validate_policy(policy: dict[str, Any]) -> None:
    for key in ("schemaVersion", "policyId", "version"):
        _required_string(policy, key)
    limits = policy.get("limits")
    if not isinstance(limits, dict) or not limits:
        raise SchedulerError("limits must be a non-empty object")
    for dimension, maximum in limits.items():
        if not isinstance(dimension, str) or not dimension:
            raise SchedulerError("quota dimension must be a non-empty string")
        if _nonnegative_int(maximum, f"limits.{dimension}") < 1:
            raise SchedulerError("quota limits must be at least 1")
    aging = policy.get("agingWindowSeconds")
    if not isinstance(aging, int) or isinstance(aging, bool) or aging < 1:
        raise SchedulerError("agingWindowSeconds must be a positive integer")
    if not isinstance(policy.get("maxAgingBoost"), int) or not 0 <= policy["maxAgingBoost"] <= 5:
        raise SchedulerError("maxAgingBoost must be an integer from 0 through 5")


def validate_reservation(reservation: dict[str, Any]) -> None:
    for key in ("reservationId", "projectId", "workPackageId", "subjectRevision"):
        _required_string(reservation, key)
    claims = reservation.get("claims")
    if not isinstance(claims, list) or not claims:
        raise SchedulerError("reservation claims must be a non-empty array")
    for claim in claims:
        validate_claim(claim)
    costs = reservation.get("quotaCosts")
    if not isinstance(costs, dict):
        raise SchedulerError("reservation quotaCosts must be an object")
    for dimension, amount in costs.items():
        _nonnegative_int(amount, f"reservation quotaCosts.{dimension}")


def _effective_priority(
    candidate: dict[str, Any], now: datetime, policy: dict[str, Any]
) -> int:
    base = PRIORITY_CLASS[candidate["priorityClass"]]
    if base == 0:
        return 0
    queued = _parse_time(candidate["queuedAt"], "queuedAt")
    waited_seconds = max(0, int((now - queued).total_seconds()))
    boost = min(
        policy["maxAgingBoost"], waited_seconds // policy["agingWindowSeconds"]
    )
    return max(1, base - boost)


def _quota_reasons(
    candidate: dict[str, Any], usage: dict[str, int], limits: dict[str, int]
) -> list[str]:
    reasons = []
    for dimension, amount in sorted(candidate["quotaCosts"].items()):
        if dimension not in limits:
            reasons.append(f"unknown quota dimension: {dimension}")
            continue
        if usage.get(dimension, 0) + amount > limits[dimension]:
            reasons.append(f"quota exceeded: {dimension}")
    return reasons


def _conflict_reasons(
    candidate: dict[str, Any], reservations: Iterable[dict[str, Any]]
) -> list[str]:
    reasons: set[str] = set()
    for reservation in reservations:
        for left in candidate["claims"]:
            for right in reservation["claims"]:
                if claims_conflict(left, right):
                    reasons.add(
                        f"conflict domain {left['domain']} held by {reservation['workPackageId']}"
                    )
    return sorted(reasons)


def schedule(
    candidates: Iterable[dict[str, Any]],
    active_reservations: Iterable[dict[str, Any]],
    policy: dict[str, Any],
    *,
    completed_dependencies: Iterable[str],
    current_revisions: dict[str, str],
    state_revision: str,
    now: str,
) -> SchedulePlan:
    """Build one deterministic scheduling decision from one state revision."""

    validate_policy(policy)
    if not state_revision.strip():
        raise SchedulerError("state_revision must be a non-empty string")
    current_time = _parse_time(now, "now")
    completed = set(completed_dependencies)
    candidate_list = list(candidates)
    reservations = list(active_reservations)
    for item in candidate_list:
        validate_candidate(item)
    for item in reservations:
        validate_reservation(item)
    ids = [item["workPackageId"] for item in candidate_list]
    if len(ids) != len(set(ids)):
        raise SchedulerError("candidate workPackageId values must be unique")
    project_ids = {item["projectId"] for item in candidate_list + reservations}
    if len(project_ids) > 1:
        raise SchedulerError("one schedule cannot span multiple projects")

    usage = {dimension: 0 for dimension in policy["limits"]}
    for reservation in reservations:
        for dimension, amount in reservation["quotaCosts"].items():
            usage[dimension] = usage.get(dimension, 0) + amount

    ordered = sorted(
        candidate_list,
        key=lambda item: (
            _effective_priority(item, current_time, policy),
            -item["userPriority"],
            _parse_time(item["queuedAt"], "queuedAt"),
            item["workPackageId"],
        ),
    )
    selected_reservations: list[dict[str, Any]] = []
    entries: list[ScheduleEntry] = []
    selected: list[str] = []
    for candidate in ordered:
        reasons: list[str] = []
        missing = sorted(set(candidate["dependencyIds"]) - completed)
        reasons.extend(f"dependency incomplete: {item}" for item in missing)
        current = current_revisions.get(candidate["workPackageId"])
        if current is None:
            reasons.append("current subject revision is unknown")
        elif current != candidate["subjectRevision"]:
            reasons.append("subject revision is stale")
        reasons.extend(_conflict_reasons(candidate, reservations + selected_reservations))
        reasons.extend(_quota_reasons(candidate, usage, policy["limits"]))
        priority = _effective_priority(candidate, current_time, policy)
        if reasons:
            entries.append(
                ScheduleEntry(
                    candidate["workPackageId"],
                    ScheduleDecision.DEFERRED,
                    tuple(dict.fromkeys(reasons)),
                    priority,
                )
            )
            continue
        selected.append(candidate["workPackageId"])
        entries.append(
            ScheduleEntry(
                candidate["workPackageId"],
                ScheduleDecision.SELECTED,
                ("eligible and capacity reserved",),
                priority,
            )
        )
        reservation = {
            "reservationId": f"planned:{state_revision}:{candidate['workPackageId']}",
            "projectId": candidate["projectId"],
            "workPackageId": candidate["workPackageId"],
            "subjectRevision": candidate["subjectRevision"],
            "claims": candidate["claims"],
            "quotaCosts": candidate["quotaCosts"],
        }
        selected_reservations.append(reservation)
        for dimension, amount in candidate["quotaCosts"].items():
            usage[dimension] = usage.get(dimension, 0) + amount

    return SchedulePlan(now, state_revision, tuple(entries), tuple(selected))


def build_integration_batch(
    completions: Iterable[dict[str, Any]],
    *,
    batch_id: str,
    target_revision: str,
    owner_role: str,
    required_checks: Iterable[str],
) -> dict[str, Any]:
    if not batch_id.strip() or not target_revision.strip() or not owner_role.strip():
        raise SchedulerError("batch identity, target revision, and owner role are required")
    checks = tuple(required_checks)
    if not checks or any(not isinstance(item, str) or not item for item in checks):
        raise SchedulerError("required_checks must contain non-empty strings")
    if len(checks) != len(set(checks)):
        raise SchedulerError("required_checks contains duplicates")
    items = list(completions)
    if not items:
        raise SchedulerError("at least one completion is required")
    member_ids: set[str] = set()
    project_ids: set[str] = set()
    integration_groups: set[str] = set()
    members = []
    for item in items:
        for key in (
            "projectId",
            "workPackageId",
            "subjectRevision",
            "baseRevision",
            "integrationGroup",
            "artifactDigest",
        ):
            _required_string(item, key)
        if item.get("status") != "completed":
            raise SchedulerError("only completed work can enter integration")
        _strings(item.get("evidenceIds"), "evidenceIds", minimum=1)
        if item["workPackageId"] in member_ids:
            raise SchedulerError("integration members must be unique")
        if item["baseRevision"] != target_revision:
            raise SchedulerError("integration member uses a stale base revision")
        member_ids.add(item["workPackageId"])
        project_ids.add(item["projectId"])
        integration_groups.add(item["integrationGroup"])
        members.append(
            {
                "workPackageId": item["workPackageId"],
                "subjectRevision": item["subjectRevision"],
                "artifactDigest": item["artifactDigest"],
                "evidenceIds": item["evidenceIds"],
            }
        )
    if len(project_ids) != 1:
        raise SchedulerError("integration batch cannot span projects")
    if len(integration_groups) != 1:
        raise SchedulerError("integration batch cannot span integration groups")
    batch = {
        "schemaVersion": "0.1",
        "batchId": batch_id,
        "projectId": next(iter(project_ids)),
        "integrationGroup": next(iter(integration_groups)),
        "targetRevision": target_revision,
        "ownerRole": owner_role,
        "requiredChecks": list(checks),
        "members": sorted(members, key=lambda item: item["workPackageId"]),
    }
    batch["batchDigest"] = canonical_digest(batch)
    return batch


def validate_integration_batch(batch: dict[str, Any]) -> None:
    for key in (
        "schemaVersion",
        "batchId",
        "projectId",
        "integrationGroup",
        "targetRevision",
        "ownerRole",
        "batchDigest",
    ):
        _required_string(batch, key)
    _strings(batch.get("requiredChecks"), "requiredChecks", minimum=1)
    members = batch.get("members")
    if not isinstance(members, list) or not members:
        raise SchedulerError("integration members must be a non-empty array")
    ids: list[str] = []
    for member in members:
        if not isinstance(member, dict):
            raise SchedulerError("each integration member must be an object")
        for key in ("workPackageId", "subjectRevision", "artifactDigest"):
            _required_string(member, key)
        if len(member["artifactDigest"]) != 64 or any(
            char not in "0123456789abcdef" for char in member["artifactDigest"]
        ):
            raise SchedulerError("artifactDigest must be a lowercase SHA-256 digest")
        _strings(member.get("evidenceIds"), "evidenceIds", minimum=1)
        ids.append(member["workPackageId"])
    if len(ids) != len(set(ids)):
        raise SchedulerError("integration members must be unique")
    if ids != sorted(ids):
        raise SchedulerError("integration members must use stable ordering")
    unsigned = dict(batch)
    supplied = unsigned.pop("batchDigest")
    if canonical_digest(unsigned) != supplied:
        raise SchedulerError("integration batch digest does not match content")


def validate_integration_result(result: dict[str, Any], batch: dict[str, Any]) -> None:
    validate_integration_batch(batch)
    for key in (
        "schemaVersion",
        "batchId",
        "batchDigest",
        "targetRevision",
        "status",
        "summary",
    ):
        _required_string(result, key)
    if result["status"] not in TERMINAL_INTEGRATION:
        raise SchedulerError("integration status is invalid")
    if result["batchId"] != batch["batchId"] or result["batchDigest"] != batch["batchDigest"]:
        raise SchedulerError("integration result does not match batch")
    if result["targetRevision"] != batch["targetRevision"]:
        raise SchedulerError("integration result uses the wrong target revision")
    check_results = result.get("checkResults")
    if not isinstance(check_results, dict):
        raise SchedulerError("checkResults must be an object")
    if set(check_results) != set(batch["requiredChecks"]):
        raise SchedulerError("integration result must report every required check exactly once")
    if any(value not in {"passed", "failed", "inconclusive"} for value in check_results.values()):
        raise SchedulerError("integration check result is invalid")
    evidence = _strings(result.get("evidenceIds"), "evidenceIds")
    resulting_revision = result.get("resultingRevision")
    if result["status"] == "passed":
        if any(value != "passed" for value in check_results.values()):
            raise SchedulerError("passed integration requires every check to pass")
        if not evidence:
            raise SchedulerError("passed integration requires evidence")
        if not isinstance(resulting_revision, str) or not resulting_revision.strip():
            raise SchedulerError("passed integration requires a resulting revision")
        if resulting_revision == batch["targetRevision"]:
            raise SchedulerError("resulting revision must differ from target revision")
    elif resulting_revision is not None:
        raise SchedulerError("non-passed integration cannot claim a resulting revision")
