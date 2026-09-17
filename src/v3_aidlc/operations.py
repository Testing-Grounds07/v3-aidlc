"""Operational telemetry, SLO, usage, recovery, and readiness contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable


class OperationsError(ValueError):
    """Raised when operational data is unsafe or internally inconsistent."""


class BudgetDecision(StrEnum):
    WITHIN = "within"
    WARN = "warn"
    BLOCK = "block"


class ReadinessOutcome(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    INCONCLUSIVE = "inconclusive"


PROHIBITED_TELEMETRY_KEYS = {
    "prompt",
    "response",
    "content",
    "secret",
    "token",
    "credential",
    "authorization",
    "cookie",
}
SIGNAL_KINDS = {"trace", "metric", "log", "audit"}
SENSITIVITIES = {"public", "internal", "confidential", "restricted"}
SLI_KINDS = {"availability", "success_ratio", "latency_ms", "durability", "recovery_seconds"}
MIGRATION_PHASES = ("expand", "backfill", "verify", "switch", "contract")


@dataclass(frozen=True)
class SLOEvaluation:
    slo_id: str
    met: bool
    observed: float
    target: float
    error_budget_total: float
    error_budget_remaining: float


@dataclass(frozen=True)
class BudgetEvaluation:
    budget_id: str
    decision: BudgetDecision
    actual: int
    limit: int
    remaining: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReadinessEvaluation:
    outcome: ReadinessOutcome
    missing_controls: tuple[str, ...]
    failed_controls: tuple[str, ...]
    reasons: tuple[str, ...]


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise OperationsError(f"{key} must be a non-empty string")
    return result


def _strings(value: Any, key: str, *, minimum: int = 0) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise OperationsError(f"{key} must be a string array")
    if len(value) < minimum:
        raise OperationsError(f"{key} must contain at least {minimum} item(s)")
    if len(value) != len(set(value)):
        raise OperationsError(f"{key} contains duplicates")
    return tuple(value)


def _parse_time(value: Any, key: str) -> datetime:
    if not isinstance(value, str):
        raise OperationsError(f"{key} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OperationsError(f"{key} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise OperationsError(f"{key} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _nonnegative_int(value: Any, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OperationsError(f"{key} must be a non-negative integer")
    return value


def validate_telemetry(record: dict[str, Any]) -> None:
    for key in ("recordId", "traceId", "projectId", "signalKind", "name", "timestamp", "sensitivity"):
        _required_string(record, key)
    if record["signalKind"] not in SIGNAL_KINDS:
        raise OperationsError("signalKind is invalid")
    if record["sensitivity"] not in SENSITIVITIES:
        raise OperationsError("sensitivity is invalid")
    _parse_time(record["timestamp"], "timestamp")
    if not isinstance(record.get("redacted"), bool):
        raise OperationsError("redacted must be boolean")
    attributes = record.get("attributes")
    if not isinstance(attributes, dict):
        raise OperationsError("attributes must be an object")
    prohibited = sorted(
        key for key in attributes if any(term in key.lower() for term in PROHIBITED_TELEMETRY_KEYS)
    )
    if prohibited:
        raise OperationsError(f"telemetry contains prohibited attributes: {prohibited}")
    for key, value in attributes.items():
        if not isinstance(key, str) or not key or not isinstance(value, (str, int, float, bool)):
            raise OperationsError("telemetry attributes must be scalar values")
    if record["signalKind"] == "trace":
        _required_string(record, "spanId")


def validate_slo(slo: dict[str, Any]) -> None:
    for key in ("sloId", "service", "sliKind", "window"):
        _required_string(slo, key)
    if slo["sliKind"] not in SLI_KINDS:
        raise OperationsError("sliKind is invalid")
    target = slo.get("target")
    if not isinstance(target, (int, float)) or isinstance(target, bool) or target < 0:
        raise OperationsError("target must be non-negative")
    if slo["sliKind"] in {"availability", "success_ratio", "durability"} and target > 1:
        raise OperationsError("ratio target cannot exceed 1")
    if not isinstance(slo.get("minimumSamples"), int) or slo["minimumSamples"] < 1:
        raise OperationsError("minimumSamples must be a positive integer")


def evaluate_slo(slo: dict[str, Any], observations: Iterable[float]) -> SLOEvaluation:
    validate_slo(slo)
    values = tuple(observations)
    if len(values) < slo["minimumSamples"]:
        raise OperationsError("insufficient samples for SLO evaluation")
    if any(not isinstance(item, (int, float)) or isinstance(item, bool) or item < 0 for item in values):
        raise OperationsError("SLO observations must be non-negative numbers")
    kind = slo["sliKind"]
    if kind in {"availability", "success_ratio", "durability"}:
        if any(item > 1 for item in values):
            raise OperationsError("ratio observations cannot exceed 1")
        observed = sum(values) / len(values)
        met = observed >= slo["target"]
        total = 1 - slo["target"]
        remaining = total - (1 - observed)
    else:
        ordered = sorted(values)
        percentile = slo.get("percentile", 0.95)
        if not isinstance(percentile, (int, float)) or not 0 < percentile <= 1:
            raise OperationsError("percentile must be greater than 0 and at most 1")
        index = max(0, min(len(ordered) - 1, int(len(ordered) * percentile + 0.999999) - 1))
        observed = float(ordered[index])
        met = observed <= slo["target"]
        total = float(slo["target"])
        remaining = float(slo["target"]) - observed
    return SLOEvaluation(slo["sloId"], met, observed, float(slo["target"]), total, remaining)


def validate_usage(entry: dict[str, Any]) -> None:
    for key in ("entryId", "projectId", "workPackageId", "runId", "provider", "model", "occurredAt", "currency"):
        _required_string(entry, key)
    _parse_time(entry["occurredAt"], "occurredAt")
    for key in ("inputUnits", "outputUnits", "toolSeconds", "storageByteHours", "costMicros"):
        _nonnegative_int(entry.get(key), key)
    if len(entry["currency"]) != 3 or not entry["currency"].isupper():
        raise OperationsError("currency must be an uppercase ISO-style code")


def aggregate_usage(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = tuple(entries)
    seen: set[str] = set()
    totals = {"inputUnits": 0, "outputUnits": 0, "toolSeconds": 0, "storageByteHours": 0, "costMicros": 0}
    currencies: set[str] = set()
    for entry in items:
        validate_usage(entry)
        if entry["entryId"] in seen:
            raise OperationsError(f"duplicate usage entry: {entry['entryId']}")
        seen.add(entry["entryId"])
        currencies.add(entry["currency"])
        for key in totals:
            totals[key] += entry[key]
    if len(currencies) > 1:
        raise OperationsError("usage aggregation cannot mix currencies")
    return {**totals, "currency": next(iter(currencies), "USD"), "entryCount": len(items)}


def evaluate_budget(budget: dict[str, Any], actual: int) -> BudgetEvaluation:
    for key in ("budgetId", "dimension", "period"):
        _required_string(budget, key)
    limit = _nonnegative_int(budget.get("limit"), "limit")
    warn_at = _nonnegative_int(budget.get("warnAt"), "warnAt")
    actual = _nonnegative_int(actual, "actual")
    if limit < 1 or warn_at > limit:
        raise OperationsError("budget thresholds are invalid")
    if actual > limit:
        decision = BudgetDecision.BLOCK
        reasons = ("budget limit exceeded",)
    elif actual >= warn_at:
        decision = BudgetDecision.WARN
        reasons = ("budget warning threshold reached",)
    else:
        decision = BudgetDecision.WITHIN
        reasons = ("budget remains available",)
    return BudgetEvaluation(budget["budgetId"], decision, actual, limit, limit - actual, reasons)


def assess_restore(policy: dict[str, Any], observation: dict[str, Any], *, now: str) -> tuple[bool, tuple[str, ...]]:
    for key in ("policyId", "dataSet"):
        _required_string(policy, key)
    rpo = _nonnegative_int(policy.get("rpoSeconds"), "rpoSeconds")
    rto = _nonnegative_int(policy.get("rtoSeconds"), "rtoSeconds")
    _required_string(observation, "backupId")
    created = _parse_time(observation.get("createdAt"), "createdAt")
    restored = _nonnegative_int(observation.get("restoreDurationSeconds"), "restoreDurationSeconds")
    current = _parse_time(now, "now")
    reasons = []
    if (current - created).total_seconds() > rpo:
        reasons.append("recovery point objective is not met")
    if restored > rto:
        reasons.append("recovery time objective is not met")
    for key in ("encrypted", "integrityVerified", "restoreTestPassed"):
        if observation.get(key) is not True:
            reasons.append(f"{key} is not satisfied")
    return not reasons, tuple(reasons)


def validate_migration(migration: dict[str, Any]) -> None:
    for key in ("migrationId", "fromVersion", "toVersion", "currentPhase", "rollbackProcedure"):
        _required_string(migration, key)
    if migration["fromVersion"] == migration["toVersion"]:
        raise OperationsError("migration versions must differ")
    if migration["currentPhase"] not in MIGRATION_PHASES:
        raise OperationsError("currentPhase is invalid")
    completed = _strings(migration.get("completedPhases"), "completedPhases")
    current_index = MIGRATION_PHASES.index(migration["currentPhase"])
    if tuple(completed) != MIGRATION_PHASES[:current_index]:
        raise OperationsError("completed migration phases are not contiguous")
    if not isinstance(migration.get("backwardCompatible"), bool):
        raise OperationsError("backwardCompatible must be boolean")
    if current_index < MIGRATION_PHASES.index("switch") and not migration["backwardCompatible"]:
        raise OperationsError("pre-switch migration must remain backward compatible")
    evidence = migration.get("phaseEvidence")
    if not isinstance(evidence, dict):
        raise OperationsError("phaseEvidence must be an object")
    missing = set(completed) - set(evidence)
    if missing:
        raise OperationsError(f"completed phases lack evidence: {sorted(missing)}")


def validate_topology(topology: dict[str, Any]) -> None:
    for key in ("topologyId", "environment"):
        _required_string(topology, key)
    components = topology.get("components")
    if not isinstance(components, list) or not components:
        raise OperationsError("components must be a non-empty array")
    ids = []
    state_authorities = 0
    for component in components:
        for key in ("id", "role", "trustZone", "dataClassification"):
            _required_string(component, key)
        ids.append(component["id"])
        if not isinstance(component.get("replicas"), int) or component["replicas"] < 1:
            raise OperationsError("component replicas must be positive")
        if not isinstance(component.get("stateAuthority"), bool):
            raise OperationsError("stateAuthority must be boolean")
        state_authorities += int(component["stateAuthority"])
    if len(ids) != len(set(ids)):
        raise OperationsError("component IDs must be unique")
    if state_authorities != 1:
        raise OperationsError("topology must declare exactly one logical state authority")
    edges = topology.get("connections")
    if not isinstance(edges, list):
        raise OperationsError("connections must be an array")
    known = set(ids)
    for edge in edges:
        if edge.get("source") not in known or edge.get("target") not in known:
            raise OperationsError("connection references an unknown component")
        if edge.get("encrypted") is not True:
            raise OperationsError("component connections must be encrypted")


def evaluate_readiness(
    checklist: dict[str, Any], evidence: Iterable[dict[str, Any]]
) -> ReadinessEvaluation:
    _required_string(checklist, "checklistId")
    controls = checklist.get("controls")
    if not isinstance(controls, list) or not controls:
        raise OperationsError("controls must be a non-empty array")
    by_id = {}
    for item in evidence:
        control_id = _required_string(item, "controlId")
        if control_id in by_id:
            raise OperationsError(f"duplicate readiness evidence: {control_id}")
        if item.get("status") not in {"passed", "failed", "inconclusive"}:
            raise OperationsError("readiness evidence status is invalid")
        _strings(item.get("evidenceIds"), "evidenceIds", minimum=1)
        by_id[control_id] = item
    missing = []
    failed = []
    inconclusive = []
    for control in controls:
        control_id = _required_string(control, "id")
        if control.get("required") is not True:
            continue
        result = by_id.get(control_id)
        if result is None:
            missing.append(control_id)
        elif result["status"] == "failed":
            failed.append(control_id)
        elif result["status"] == "inconclusive":
            inconclusive.append(control_id)
    reasons = [f"required control missing: {item}" for item in missing]
    reasons += [f"required control failed: {item}" for item in failed]
    reasons += [f"required control inconclusive: {item}" for item in inconclusive]
    if missing or inconclusive:
        outcome = ReadinessOutcome.INCONCLUSIVE
    elif failed:
        outcome = ReadinessOutcome.NOT_READY
    else:
        outcome = ReadinessOutcome.READY
        reasons = ["all required production-readiness controls passed"]
    return ReadinessEvaluation(outcome, tuple(missing), tuple(failed), tuple(reasons))
