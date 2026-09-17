"""Append-only event integrity, findings, learning, and safe recovery planning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable


ZERO_HASH = "0" * 64
ACTOR_TYPES = {"user", "liaison", "project_lead", "agent", "tool", "system"}
FINDING_CATEGORIES = {
    "defect",
    "risk",
    "evidence_gap",
    "security",
    "compliance",
    "ambiguity",
    "integration",
    "operations",
}
SEVERITIES = {"info", "low", "medium", "high", "critical"}
FINDING_STATUSES = {
    "open",
    "acknowledged",
    "repairing",
    "resolved",
    "accepted_risk",
    "superseded",
}
LEARNING_TYPES = {
    "validated_fact",
    "negative_result",
    "hypothesis",
    "decision_rule",
    "pattern",
    "counterexample",
}
LEARNING_CONFIDENCE = {"tentative", "supported", "validated"}
LEARNING_STATUSES = {"active", "superseded", "retracted"}
LEASE_STATUSES = {"active", "released", "expired", "revoked"}


class RecoveryError(ValueError):
    """Raised when durable history or recovery input is unsafe or inconsistent."""


class RecoveryAction(str, Enum):
    WAIT_FOR_LEASE = "wait_for_lease"
    RECLAIM_AND_REQUEUE = "reclaim_and_requeue"
    VERIFY_EXTERNAL_EFFECT = "verify_external_effect"
    RECONCILE_COMPLETED_RUN = "reconcile_completed_run"
    RECONCILE_ORPHAN_RUN = "reconcile_orphan_run"
    ESCALATE_ATTEMPT_BUDGET = "escalate_attempt_budget"


@dataclass(frozen=True)
class RecoveryStep:
    action: RecoveryAction
    run_id: str
    lease_id: str | None
    reason: str


@dataclass(frozen=True)
class RecoveryPlan:
    generated_at: str
    verified_through_sequence: int
    steps: tuple[RecoveryStep, ...]


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise RecoveryError(f"{key} must be a non-empty string")
    return result


def _string_array(value: Any, field: str, minimum: int = 0) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise RecoveryError(f"{field} must be a string array")
    if len(value) < minimum:
        raise RecoveryError(f"{field} must contain at least {minimum} item(s)")
    if len(value) != len(set(value)):
        raise RecoveryError(f"{field} contains duplicates")
    return tuple(value)


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise RecoveryError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise RecoveryError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _event_hash(event: dict[str, Any]) -> str:
    body = {key: value for key, value in event.items() if key != "eventHash"}
    return _canonical_hash(body)


def validate_event(event: dict[str, Any]) -> None:
    for key in (
        "eventId",
        "projectId",
        "streamId",
        "eventType",
        "aggregateType",
        "aggregateId",
        "occurredAt",
        "recordedAt",
        "idempotencyKey",
        "previousEventHash",
        "eventHash",
    ):
        _required_string(event, key)
    if not isinstance(event.get("sequence"), int) or event["sequence"] < 1:
        raise RecoveryError("sequence must be a positive integer")
    actor = event.get("actor")
    if not isinstance(actor, dict):
        raise RecoveryError("actor must be an object")
    _required_string(actor, "id")
    if actor.get("type") not in ACTOR_TYPES:
        raise RecoveryError(f"Unknown actor type: {actor.get('type')}")
    if not isinstance(event.get("payload"), dict):
        raise RecoveryError("payload must be an object")
    occurred = _parse_time(event["occurredAt"], "occurredAt")
    recorded = _parse_time(event["recordedAt"], "recordedAt")
    if occurred > recorded:
        raise RecoveryError("occurredAt cannot be after recordedAt")
    for field in ("previousEventHash", "eventHash"):
        if len(event[field]) != 64 or any(ch not in "0123456789abcdef" for ch in event[field]):
            raise RecoveryError(f"{field} must be a lowercase SHA-256 digest")


def append_event(
    history: Iterable[dict[str, Any]], draft: dict[str, Any]
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any], bool]:
    """Append once by idempotency key; identical retries return the existing event."""

    events = tuple(history)
    verify_event_chain(events)
    for existing in events:
        if existing["idempotencyKey"] == draft.get("idempotencyKey"):
            comparable = {
                key: value
                for key, value in existing.items()
                if key not in {"sequence", "previousEventHash", "eventHash"}
            }
            if comparable != draft:
                raise RecoveryError("Idempotency key was reused with different event data")
            return events, existing, False

    event = dict(draft)
    event["sequence"] = len(events) + 1
    event["previousEventHash"] = events[-1]["eventHash"] if events else ZERO_HASH
    event["eventHash"] = _event_hash(event)
    validate_event(event)
    updated = events + (event,)
    verify_event_chain(updated)
    return updated, event, True


def verify_event_chain(events: Iterable[dict[str, Any]]) -> None:
    expected_hash = ZERO_HASH
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    seen_event_ids: set[str] = set()
    project_id: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        validate_event(event)
        if event["sequence"] != expected_sequence:
            raise RecoveryError("Event sequence is not contiguous")
        if project_id is None:
            project_id = event["projectId"]
        elif event["projectId"] != project_id:
            raise RecoveryError("Event chain contains more than one project")
        if event["eventId"] in seen_ids:
            raise RecoveryError(f"Duplicate event ID: {event['eventId']}")
        if event["idempotencyKey"] in seen_keys:
            raise RecoveryError(f"Duplicate idempotency key: {event['idempotencyKey']}")
        if event["previousEventHash"] != expected_hash:
            raise RecoveryError("Event hash chain is broken")
        if event["eventHash"] != _event_hash(event):
            raise RecoveryError("Event content hash is invalid")
        causation = event.get("causationId")
        if causation is not None and causation not in seen_event_ids:
            raise RecoveryError("causationId must reference an earlier event")
        seen_ids.add(event["eventId"])
        seen_event_ids.add(event["eventId"])
        seen_keys.add(event["idempotencyKey"])
        expected_hash = event["eventHash"]


def validate_finding(finding: dict[str, Any]) -> None:
    for key in (
        "id",
        "projectId",
        "subjectId",
        "subjectRevision",
        "sourceEventId",
        "category",
        "severity",
        "status",
        "summary",
        "details",
        "ownerRole",
        "discoveredAt",
    ):
        _required_string(finding, key)
    if finding["category"] not in FINDING_CATEGORIES:
        raise RecoveryError(f"Unknown finding category: {finding['category']}")
    if finding["severity"] not in SEVERITIES:
        raise RecoveryError(f"Unknown finding severity: {finding['severity']}")
    if finding["status"] not in FINDING_STATUSES:
        raise RecoveryError(f"Unknown finding status: {finding['status']}")
    _string_array(finding.get("evidenceIds", []), "evidenceIds")
    _parse_time(finding["discoveredAt"], "discoveredAt")
    if finding["status"] in {"resolved", "accepted_risk", "superseded"}:
        _required_string(finding, "resolution")
        _required_string(finding, "resolutionEventId")
        _parse_time(_required_string(finding, "resolvedAt"), "resolvedAt")
        if finding["status"] == "resolved":
            _string_array(
                finding.get("resolutionEvidenceIds"),
                "resolutionEvidenceIds",
                minimum=1,
            )
        if finding["status"] == "accepted_risk":
            _required_string(finding, "decisionId")
        if finding["status"] == "superseded":
            _required_string(finding, "supersededByFindingId")
    elif any(key in finding for key in ("resolution", "resolutionEventId", "resolvedAt")):
        raise RecoveryError("Open findings cannot claim a terminal resolution")


FINDING_TRANSITIONS = {
    "open": {"acknowledged", "repairing", "resolved", "accepted_risk", "superseded"},
    "acknowledged": {"repairing", "resolved", "accepted_risk", "superseded"},
    "repairing": {"acknowledged", "resolved", "accepted_risk", "superseded"},
    "resolved": set(),
    "accepted_risk": {"repairing", "resolved", "superseded"},
    "superseded": set(),
}


def require_finding_transition(current: str, requested: str) -> None:
    if current not in FINDING_TRANSITIONS or requested not in FINDING_STATUSES:
        raise RecoveryError("Unknown finding state")
    if requested not in FINDING_TRANSITIONS[current]:
        raise RecoveryError(f"Finding cannot transition from {current} to {requested}")


def validate_learning(learning: dict[str, Any]) -> None:
    for key in (
        "id",
        "projectId",
        "learningType",
        "confidence",
        "status",
        "statement",
        "createdAt",
        "createdBy",
    ):
        _required_string(learning, key)
    if learning["learningType"] not in LEARNING_TYPES:
        raise RecoveryError(f"Unknown learning type: {learning['learningType']}")
    if learning["confidence"] not in LEARNING_CONFIDENCE:
        raise RecoveryError(f"Unknown learning confidence: {learning['confidence']}")
    if learning["status"] not in LEARNING_STATUSES:
        raise RecoveryError(f"Unknown learning status: {learning['status']}")
    source_findings = _string_array(
        learning.get("sourceFindingIds", []), "sourceFindingIds"
    )
    source_events = _string_array(learning.get("sourceEventIds", []), "sourceEventIds")
    evidence = _string_array(learning.get("evidenceIds", []), "evidenceIds")
    if not (source_findings or source_events or evidence):
        raise RecoveryError("Learning must retain at least one source reference")
    _string_array(learning.get("applicabilityTags", []), "applicabilityTags", minimum=1)
    _parse_time(learning["createdAt"], "createdAt")
    if learning["confidence"] == "validated" and not evidence:
        raise RecoveryError("Validated learning requires evidence")
    if learning["status"] in {"superseded", "retracted"}:
        _required_string(learning, "statusReason")
        _required_string(learning, "statusEventId")


def validate_lease(lease: dict[str, Any]) -> None:
    for key in (
        "leaseId",
        "projectId",
        "resourceType",
        "resourceId",
        "holderRunId",
        "acquiredAt",
        "heartbeatAt",
        "expiresAt",
        "status",
        "contextManifestId",
        "dispatchDigest",
        "idempotencyKey",
    ):
        _required_string(lease, key)
    if lease["status"] not in LEASE_STATUSES:
        raise RecoveryError(f"Unknown lease status: {lease['status']}")
    if not isinstance(lease.get("attempt"), int) or lease["attempt"] < 1:
        raise RecoveryError("Lease attempt must be a positive integer")
    acquired = _parse_time(lease["acquiredAt"], "acquiredAt")
    heartbeat = _parse_time(lease["heartbeatAt"], "heartbeatAt")
    expires = _parse_time(lease["expiresAt"], "expiresAt")
    if not acquired <= heartbeat <= expires:
        raise RecoveryError("Lease times must satisfy acquiredAt <= heartbeatAt <= expiresAt")
    if len(lease["dispatchDigest"]) != 64 or any(
        ch not in "0123456789abcdef" for ch in lease["dispatchDigest"]
    ):
        raise RecoveryError("dispatchDigest must be a SHA-256 digest")


def plan_recovery(
    events: Iterable[dict[str, Any]],
    leases: Iterable[dict[str, Any]],
    effect_observations: dict[str, str],
    generated_at: str,
    max_attempts: int,
) -> RecoveryPlan:
    events = tuple(events)
    verify_event_chain(events)
    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise RecoveryError("max_attempts must be a positive integer")
    now = _parse_time(generated_at, "generatedAt")

    dispatches: dict[str, dict[str, Any]] = {}
    completed_runs: set[str] = set()
    for event in events:
        if event["eventType"] == "run.dispatched":
            run_id = _required_string(event["payload"], "runId")
            if run_id in dispatches:
                raise RecoveryError(f"Run was dispatched more than once: {run_id}")
            dispatches[run_id] = event
        elif event["eventType"] == "run.completed":
            completed_runs.add(_required_string(event["payload"], "runId"))

    lease_by_run: dict[str, dict[str, Any]] = {}
    for lease in leases:
        validate_lease(lease)
        run_id = lease["holderRunId"]
        if run_id in lease_by_run:
            raise RecoveryError(f"Multiple current leases for run: {run_id}")
        lease_by_run[run_id] = lease

    steps: list[RecoveryStep] = []
    for run_id in sorted(dispatches):
        event = dispatches[run_id]
        lease = lease_by_run.get(run_id)
        if run_id in completed_runs:
            if lease is not None and lease["status"] == "active":
                steps.append(
                    RecoveryStep(
                        RecoveryAction.RECONCILE_COMPLETED_RUN,
                        run_id,
                        lease["leaseId"],
                        "The run completed but its lease remains active.",
                    )
                )
            continue
        if lease is None:
            steps.append(
                RecoveryStep(
                    RecoveryAction.RECONCILE_ORPHAN_RUN,
                    run_id,
                    None,
                    "The dispatch has no durable current lease.",
                )
            )
            continue
        if lease["status"] != "active":
            steps.append(
                RecoveryStep(
                    RecoveryAction.RECONCILE_ORPHAN_RUN,
                    run_id,
                    lease["leaseId"],
                    f"The unfinished run has a {lease['status']} lease.",
                )
            )
            continue
        if now <= _parse_time(lease["expiresAt"], "expiresAt"):
            steps.append(
                RecoveryStep(
                    RecoveryAction.WAIT_FOR_LEASE,
                    run_id,
                    lease["leaseId"],
                    "The current lease has not expired.",
                )
            )
            continue

        effect_key = event["payload"].get("effectKey")
        effect_status = effect_observations.get(effect_key) if effect_key else None
        if effect_status == "succeeded":
            steps.append(
                RecoveryStep(
                    RecoveryAction.RECONCILE_COMPLETED_RUN,
                    run_id,
                    lease["leaseId"],
                    "The external effect already succeeded; do not repeat it.",
                )
            )
        elif event["payload"].get("externalSideEffectPossible") is True:
            steps.append(
                RecoveryStep(
                    RecoveryAction.VERIFY_EXTERNAL_EFFECT,
                    run_id,
                    lease["leaseId"],
                    "The lease expired after a potentially external effect; verify reality before retrying.",
                )
            )
        elif lease["attempt"] >= max_attempts:
            steps.append(
                RecoveryStep(
                    RecoveryAction.ESCALATE_ATTEMPT_BUDGET,
                    run_id,
                    lease["leaseId"],
                    "The safe retry budget is exhausted.",
                )
            )
        else:
            steps.append(
                RecoveryStep(
                    RecoveryAction.RECLAIM_AND_REQUEUE,
                    run_id,
                    lease["leaseId"],
                    "The lease expired, no external effect is possible, and retry budget remains.",
                )
            )

    return RecoveryPlan(
        generated_at=generated_at,
        verified_through_sequence=len(events),
        steps=tuple(steps),
    )
