"""Evidence admissibility and deterministic gate evaluation for V3-AIDLC."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


EVIDENCE_KINDS = {
    "artifact",
    "test_result",
    "build_result",
    "review_disposition",
    "scan_result",
    "observation",
    "metric",
    "decision",
    "provenance_manifest",
}
CHECK_METHODS = {"deterministic", "semantic_review", "human_verification"}
GATE_TYPES = {"package", "bolt", "stage", "integration", "promotion", "release"}
REQUIREMENTS = {"required", "conditional", "advisory"}
CHECK_STATUSES = {"passed", "failed", "inconclusive", "error"}
PREDICATE_KEYS = {"equals", "in"}
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class EvidenceGateError(ValueError):
    """Raised when evidence or gate data cannot be safely evaluated."""


class GateOutcome(str, Enum):
    PASSED = "passed"
    PASSED_WITH_EXCEPTION = "passed_with_exception"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class CheckAssessment:
    check_id: str
    declared_status: str
    admissible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class GateEvaluation:
    gate_id: str
    gate_version: str
    subject_id: str
    subject_revision: str
    outcome: GateOutcome
    promotable: bool
    required_checks: tuple[str, ...]
    advisory_checks: tuple[str, ...]
    missing_checks: tuple[str, ...]
    invalid_checks: tuple[str, ...]
    accepted_exceptions: tuple[str, ...]
    reasons: tuple[str, ...]


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceGateError(f"Cannot load {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceGateError(f"{label} {path} must contain a JSON object")
    return value


def load_contract(path: Path) -> dict[str, Any]:
    return _load_json(path, "contract")


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise EvidenceGateError(f"{key} must be a non-empty string")
    return result


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise EvidenceGateError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise EvidenceGateError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_predicate(predicate: Any) -> None:
    if not isinstance(predicate, dict):
        raise EvidenceGateError("Each condition predicate must be an object")
    _required_string(predicate, "fact")
    operators = PREDICATE_KEYS.intersection(predicate)
    if len(operators) != 1:
        raise EvidenceGateError("Each predicate must use exactly one operator")
    if set(predicate) - {"fact"} - PREDICATE_KEYS:
        raise EvidenceGateError("Predicate contains unsupported fields")
    if "in" in predicate and (
        not isinstance(predicate["in"], list) or not predicate["in"]
    ):
        raise EvidenceGateError("Predicate 'in' must be a non-empty array")


def _matches(predicate: dict[str, Any], facts: dict[str, Any]) -> bool:
    fact = predicate["fact"]
    if fact not in facts:
        return False
    if "equals" in predicate:
        return facts[fact] == predicate["equals"]
    return facts[fact] in predicate["in"]


def validate_evidence(record: dict[str, Any]) -> None:
    for key in (
        "id",
        "kind",
        "subjectId",
        "subjectRevision",
        "producerId",
        "producerRole",
        "producerIndependenceGroup",
        "collectedAt",
        "locator",
        "sha256",
    ):
        _required_string(record, key)
    if record["kind"] not in EVIDENCE_KINDS:
        raise EvidenceGateError(f"Unknown evidence kind: {record['kind']}")
    if not DIGEST_PATTERN.fullmatch(record["sha256"]):
        raise EvidenceGateError("sha256 must contain exactly 64 lowercase hex characters")
    _parse_time(record["collectedAt"], "collectedAt")
    assertions = record.get("assertions")
    if not isinstance(assertions, list) or not assertions or any(
        not isinstance(item, str) or not item.strip() for item in assertions
    ):
        raise EvidenceGateError("assertions must be a non-empty string array")


def validate_check_contract(contract: dict[str, Any]) -> None:
    for key in ("id", "version", "title"):
        _required_string(contract, key)
    if contract.get("method") not in CHECK_METHODS:
        raise EvidenceGateError(f"Unknown check method: {contract.get('method')}")
    kinds = contract.get("acceptedEvidenceKinds")
    if not isinstance(kinds, list) or not kinds or set(kinds) - EVIDENCE_KINDS:
        raise EvidenceGateError("acceptedEvidenceKinds must contain known kinds")
    if not isinstance(contract.get("minimumEvidence"), int) or contract[
        "minimumEvidence"
    ] < 1:
        raise EvidenceGateError("minimumEvidence must be at least 1")
    max_age = contract.get("maxAgeSeconds")
    if not isinstance(max_age, int) or max_age < 0:
        raise EvidenceGateError("maxAgeSeconds must be a non-negative integer")
    if not isinstance(contract.get("requiresDigest"), bool):
        raise EvidenceGateError("requiresDigest must be boolean")
    if not isinstance(contract.get("requiresIndependentEvaluator"), bool):
        raise EvidenceGateError("requiresIndependentEvaluator must be boolean")


def validate_gate_contract(
    contract: dict[str, Any], check_library: dict[str, dict[str, Any]]
) -> None:
    for key in ("id", "version", "title"):
        _required_string(contract, key)
    if contract.get("gateType") not in GATE_TYPES:
        raise EvidenceGateError(f"Unknown gate type: {contract.get('gateType')}")
    authorities = contract.get("acceptedExceptionAuthorities")
    if not isinstance(authorities, list) or any(
        not isinstance(item, str) or not item for item in authorities
    ):
        raise EvidenceGateError("acceptedExceptionAuthorities must be a string array")
    rules = contract.get("checkRules")
    if not isinstance(rules, list) or not rules:
        raise EvidenceGateError("checkRules must be a non-empty array")
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise EvidenceGateError("Each check rule must be an object")
        check_id = _required_string(rule, "checkId")
        if check_id in seen:
            raise EvidenceGateError(f"Duplicate gate check: {check_id}")
        seen.add(check_id)
        if check_id not in check_library:
            raise EvidenceGateError(f"Gate references unknown check: {check_id}")
        validate_check_contract(check_library[check_id])
        requirement = rule.get("requirement")
        if requirement not in REQUIREMENTS:
            raise EvidenceGateError(f"Invalid requirement for {check_id}")
        conditions = rule.get("whenAll", [])
        if requirement == "conditional" and not conditions:
            raise EvidenceGateError(f"Conditional check {check_id} needs whenAll")
        if requirement != "conditional" and conditions:
            raise EvidenceGateError(f"Only conditional check {check_id} may use whenAll")
        for predicate in conditions:
            _validate_predicate(predicate)
        if not isinstance(rule.get("waivable"), bool):
            raise EvidenceGateError(f"Check {check_id} waivable must be boolean")
        if rule.get("hardControl") is True and rule.get("waivable") is True:
            raise EvidenceGateError(f"Hard-control check {check_id} cannot be waivable")


def load_check_library(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    result = {}
    for path in paths:
        contract = load_contract(path)
        validate_check_contract(contract)
        if contract["id"] in result:
            raise EvidenceGateError(f"Duplicate check ID: {contract['id']}")
        result[contract["id"]] = contract
    return result


def assess_check_result(
    result: dict[str, Any],
    contract: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
) -> CheckAssessment:
    validate_check_contract(contract)
    if result.get("checkId") != contract["id"]:
        raise EvidenceGateError("Check result does not match its contract")
    if result.get("checkVersion") != contract["version"]:
        raise EvidenceGateError("Check result uses the wrong contract version")
    status = result.get("status")
    if status not in CHECK_STATUSES:
        raise EvidenceGateError(f"Unknown check status: {status}")
    subject_id = _required_string(result, "subjectId")
    subject_revision = _required_string(result, "subjectRevision")
    evaluated_at = _parse_time(_required_string(result, "evaluatedAt"), "evaluatedAt")
    evaluator = result.get("evaluator")
    if not isinstance(evaluator, dict):
        raise EvidenceGateError("evaluator must be an object")
    for key in ("id", "role", "independenceGroup"):
        _required_string(evaluator, key)
    subject_group = _required_string(result, "subjectProducerIndependenceGroup")

    evidence_ids = result.get("evidenceIds")
    if not isinstance(evidence_ids, list) or any(
        not isinstance(item, str) or not item for item in evidence_ids
    ):
        raise EvidenceGateError("evidenceIds must be a string array")
    reasons: list[str] = []
    if len(evidence_ids) < contract["minimumEvidence"]:
        reasons.append("required evidence count is not met")
    if len(evidence_ids) != len(set(evidence_ids)):
        reasons.append("duplicate evidence IDs were supplied")
    if contract["requiresIndependentEvaluator"] and evaluator[
        "independenceGroup"
    ] == subject_group:
        reasons.append("evaluator is not independent from the subject producer")

    for evidence_id in evidence_ids:
        record = evidence_by_id.get(evidence_id)
        if record is None:
            reasons.append(f"evidence {evidence_id} is missing")
            continue
        try:
            validate_evidence(record)
        except EvidenceGateError as error:
            reasons.append(f"evidence {evidence_id} is invalid: {error}")
            continue
        if record["kind"] not in contract["acceptedEvidenceKinds"]:
            reasons.append(f"evidence {evidence_id} has an unaccepted kind")
        if record["subjectId"] != subject_id:
            reasons.append(f"evidence {evidence_id} is bound to another subject")
        if record["subjectRevision"] != subject_revision:
            reasons.append(f"evidence {evidence_id} is bound to another revision")
        collected_at = _parse_time(record["collectedAt"], "collectedAt")
        age = (evaluated_at - collected_at).total_seconds()
        if age < 0:
            reasons.append(f"evidence {evidence_id} is dated after evaluation")
        elif age > contract["maxAgeSeconds"]:
            reasons.append(f"evidence {evidence_id} is stale")

    return CheckAssessment(
        check_id=contract["id"],
        declared_status=status,
        admissible=not reasons,
        reasons=tuple(reasons),
    )


def _valid_exception(
    exception: dict[str, Any],
    gate: dict[str, Any],
    rule: dict[str, Any],
    subject_id: str,
    subject_revision: str,
    evaluated_at: datetime,
) -> tuple[bool, str]:
    if not rule["waivable"]:
        return False, "check is non-waivable"
    required = {
        "id",
        "gateId",
        "checkId",
        "subjectId",
        "subjectRevision",
        "authority",
        "grantedBy",
        "rationale",
        "expiresAt",
    }
    if required - exception.keys():
        return False, "exception is incomplete"
    if exception["gateId"] != gate["id"] or exception["checkId"] != rule["checkId"]:
        return False, "exception targets another gate or check"
    if exception["subjectId"] != subject_id or exception["subjectRevision"] != subject_revision:
        return False, "exception targets another subject revision"
    if exception["authority"] not in gate["acceptedExceptionAuthorities"]:
        return False, "exception authority is not accepted"
    if not _required_string(exception, "grantedBy") or not _required_string(
        exception, "rationale"
    ):
        return False, "exception lacks accountable rationale"
    if evaluated_at > _parse_time(exception["expiresAt"], "expiresAt"):
        return False, "exception has expired"
    return True, "valid bounded exception"


def evaluate_gate(
    gate: dict[str, Any],
    check_library: dict[str, dict[str, Any]],
    check_results: Iterable[dict[str, Any]],
    evidence_records: Iterable[dict[str, Any]],
    facts: dict[str, Any],
    subject_id: str,
    subject_revision: str,
    evaluated_at: str,
    exceptions: Iterable[dict[str, Any]] = (),
) -> GateEvaluation:
    validate_gate_contract(gate, check_library)
    evaluation_time = _parse_time(evaluated_at, "evaluatedAt")
    evidence_by_id = {}
    for record in evidence_records:
        validate_evidence(record)
        if record["id"] in evidence_by_id:
            raise EvidenceGateError(f"Duplicate evidence ID: {record['id']}")
        evidence_by_id[record["id"]] = record
    results_by_id = {}
    for result in check_results:
        check_id = result.get("checkId")
        if check_id in results_by_id:
            raise EvidenceGateError(f"Duplicate check result: {check_id}")
        results_by_id[check_id] = result
    exception_by_check = {}
    for exception in exceptions:
        check_id = exception.get("checkId")
        if check_id in exception_by_check:
            raise EvidenceGateError(f"Duplicate exception for check: {check_id}")
        exception_by_check[check_id] = exception

    required: list[str] = []
    advisory: list[str] = []
    rules_by_check = {}
    for rule in gate["checkRules"]:
        selected = rule["requirement"] == "required" or (
            rule["requirement"] == "conditional"
            and all(_matches(item, facts) for item in rule["whenAll"])
        )
        if selected:
            required.append(rule["checkId"])
            rules_by_check[rule["checkId"]] = rule
        elif rule["requirement"] == "advisory":
            advisory.append(rule["checkId"])

    missing: list[str] = []
    invalid: list[str] = []
    accepted_exceptions: list[str] = []
    failures: list[str] = []
    unresolved: list[str] = []
    reasons: list[str] = []

    for check_id in required:
        result = results_by_id.get(check_id)
        if result is None:
            missing.append(check_id)
            unresolved.append(check_id)
            reasons.append(f"Required check {check_id} has no result.")
            continue
        if result.get("subjectId") != subject_id or result.get(
            "subjectRevision"
        ) != subject_revision:
            invalid.append(check_id)
            unresolved.append(check_id)
            reasons.append(
                f"Check {check_id} is bound to another subject revision."
            )
            continue
        result_time = _parse_time(
            _required_string(result, "evaluatedAt"), "evaluatedAt"
        )
        if result_time > evaluation_time:
            invalid.append(check_id)
            unresolved.append(check_id)
            reasons.append(f"Check {check_id} is dated after the gate evaluation.")
            continue
        assessment = assess_check_result(
            result, check_library[check_id], evidence_by_id
        )
        if not assessment.admissible:
            invalid.append(check_id)
            unresolved.append(check_id)
            reasons.extend(
                f"Check {check_id}: {reason}." for reason in assessment.reasons
            )
            continue
        if assessment.declared_status == "passed":
            continue
        exception = exception_by_check.get(check_id)
        if exception is not None:
            valid, reason = _valid_exception(
                exception,
                gate,
                rules_by_check[check_id],
                subject_id,
                subject_revision,
                evaluation_time,
            )
            if valid:
                accepted_exceptions.append(exception["id"])
                reasons.append(f"Check {check_id} uses {reason}.")
                continue
            reasons.append(f"Check {check_id} exception rejected: {reason}.")
        if assessment.declared_status == "failed":
            failures.append(check_id)
            reasons.append(f"Required check {check_id} failed.")
        else:
            unresolved.append(check_id)
            reasons.append(
                f"Required check {check_id} is {assessment.declared_status}."
            )

    if failures:
        outcome = GateOutcome.FAILED
    elif unresolved:
        outcome = GateOutcome.INCONCLUSIVE
    elif accepted_exceptions:
        outcome = GateOutcome.PASSED_WITH_EXCEPTION
    else:
        outcome = GateOutcome.PASSED
    return GateEvaluation(
        gate_id=gate["id"],
        gate_version=gate["version"],
        subject_id=subject_id,
        subject_revision=subject_revision,
        outcome=outcome,
        promotable=outcome in {GateOutcome.PASSED, GateOutcome.PASSED_WITH_EXCEPTION},
        required_checks=tuple(required),
        advisory_checks=tuple(advisory),
        missing_checks=tuple(missing),
        invalid_checks=tuple(invalid),
        accepted_exceptions=tuple(accepted_exceptions),
        reasons=tuple(reasons),
    )
