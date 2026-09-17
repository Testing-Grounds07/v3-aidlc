"""AI-specific security preflight, provenance, and containment contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable


class SecurityError(ValueError):
    """Raised when security input is malformed or cannot be trusted."""


class SecurityDecision(StrEnum):
    ALLOW = "allow"
    ALLOW_ISOLATED = "allow_isolated"
    REVIEW_REQUIRED = "review_required"
    BLOCK = "block"
    CONTAIN = "contain"


TRUST_LEVELS = {"trusted_control", "governed", "verified_external", "untrusted"}
PROVENANCE_LEVELS = {"L0", "L1", "L2", "L3"}
PROVENANCE_RANK = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
SIGNATURE_STATUSES = {"verified", "unverified", "missing"}
DEPENDENCY_STATUSES = {"approved", "quarantined", "prohibited"}
VULNERABILITY_STATUSES = {"clear", "accepted", "blocked", "unknown"}
NETWORK_POLICIES = {"deny_all", "allowlist"}
WORKSPACE_ACCESS = {"none", "read", "scoped_write"}
SECRET_ACCESS = {"none", "brokered", "direct"}
SERIOUS_SIGNALS = {
    "data_exfiltration",
    "credential_access",
    "tool_escalation",
    "persistence",
    "supply_chain_tampering",
}
KNOWN_SIGNALS = SERIOUS_SIGNALS | {"prompt_injection"}


@dataclass(frozen=True)
class SecurityAssessment:
    decision: SecurityDecision
    run_id: str
    reasons: tuple[str, ...]
    required_controls: tuple[str, ...]


def assessment_to_dict(assessment: SecurityAssessment) -> dict[str, Any]:
    return {
        "schemaVersion": "0.1",
        "runId": assessment.run_id,
        "decision": assessment.decision.value,
        "reasons": list(assessment.reasons),
        "requiredControls": list(assessment.required_controls),
    }


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise SecurityError(f"{key} must be a non-empty string")
    return result


def _strings(value: Any, key: str, *, minimum: int = 0) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise SecurityError(f"{key} must be a string array")
    if len(value) < minimum:
        raise SecurityError(f"{key} must contain at least {minimum} item(s)")
    if len(value) != len(set(value)):
        raise SecurityError(f"{key} contains duplicates")
    return tuple(value)


def _parse_time(value: Any, key: str) -> datetime:
    if not isinstance(value, str):
        raise SecurityError(f"{key} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SecurityError(f"{key} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise SecurityError(f"{key} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _digest(value: str, key: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise SecurityError(f"{key} must be a lowercase SHA-256 digest")


def validate_content_descriptor(content: dict[str, Any]) -> None:
    for key in ("id", "source", "digest", "trustLevel", "scannedAt"):
        _required_string(content, key)
    _digest(content["digest"], "digest")
    if content["trustLevel"] not in TRUST_LEVELS:
        raise SecurityError("trustLevel is invalid")
    _parse_time(content["scannedAt"], "scannedAt")
    for key in ("activeContent", "containsInstructions", "usedAsAuthority"):
        if not isinstance(content.get(key), bool):
            raise SecurityError(f"{key} must be boolean")
    signals = _strings(content.get("signals"), "signals")
    unknown = set(signals) - KNOWN_SIGNALS
    if unknown:
        raise SecurityError(f"unknown security signals: {sorted(unknown)}")
    if content["trustLevel"] == "trusted_control" and content["usedAsAuthority"] is False:
        raise SecurityError("trusted control content must be used as authority")
    if content["trustLevel"] != "trusted_control" and content["usedAsAuthority"] is True:
        raise SecurityError("only trusted control content may supply runtime authority")


def validate_tool_grant(grant: dict[str, Any]) -> None:
    for key in ("grantId", "runId", "tool", "issuedAt", "expiresAt", "grantedBy"):
        _required_string(grant, key)
    _strings(grant.get("operations"), "operations", minimum=1)
    _strings(grant.get("resources"), "resources", minimum=1)
    _strings(grant.get("networkHosts"), "networkHosts")
    issued = _parse_time(grant["issuedAt"], "issuedAt")
    expires = _parse_time(grant["expiresAt"], "expiresAt")
    if expires <= issued:
        raise SecurityError("tool grant must expire after it is issued")
    if not isinstance(grant.get("revoked"), bool):
        raise SecurityError("revoked must be boolean")


def validate_credential_lease(lease: dict[str, Any]) -> None:
    for key in (
        "leaseId",
        "runId",
        "secretRef",
        "audience",
        "issuedAt",
        "expiresAt",
        "brokerId",
    ):
        _required_string(lease, key)
    if "secretValue" in lease or "token" in lease:
        raise SecurityError("credential leases may contain references, not secret values")
    _strings(lease.get("scopes"), "scopes", minimum=1)
    issued = _parse_time(lease["issuedAt"], "issuedAt")
    expires = _parse_time(lease["expiresAt"], "expiresAt")
    if expires <= issued:
        raise SecurityError("credential lease must expire after it is issued")
    for key in ("oneTime", "renewable", "revoked"):
        if not isinstance(lease.get(key), bool):
            raise SecurityError(f"{key} must be boolean")


def validate_sandbox(profile: dict[str, Any]) -> None:
    for key in ("sandboxId", "runId"):
        _required_string(profile, key)
    for key in ("ephemeral", "processIsolation", "cleanupOnExit", "telemetry"):
        if not isinstance(profile.get(key), bool):
            raise SecurityError(f"{key} must be boolean")
    if profile.get("workspaceAccess") not in WORKSPACE_ACCESS:
        raise SecurityError("workspaceAccess is invalid")
    if profile.get("networkPolicy") not in NETWORK_POLICIES:
        raise SecurityError("networkPolicy is invalid")
    if profile.get("secretAccess") not in SECRET_ACCESS:
        raise SecurityError("secretAccess is invalid")
    hosts = _strings(profile.get("networkHosts"), "networkHosts")
    if profile["networkPolicy"] == "deny_all" and hosts:
        raise SecurityError("deny_all sandbox cannot declare network hosts")
    if profile["networkPolicy"] == "allowlist" and not hosts:
        raise SecurityError("allowlist sandbox must declare at least one host")


def validate_dependency(record: dict[str, Any]) -> None:
    for key in (
        "name",
        "version",
        "source",
        "digest",
        "status",
        "signatureStatus",
        "provenanceLevel",
        "vulnerabilityStatus",
        "sbomRef",
    ):
        _required_string(record, key)
    _digest(record["digest"], "dependency digest")
    if record["status"] not in DEPENDENCY_STATUSES:
        raise SecurityError("dependency status is invalid")
    if record["signatureStatus"] not in SIGNATURE_STATUSES:
        raise SecurityError("dependency signatureStatus is invalid")
    if record["provenanceLevel"] not in PROVENANCE_LEVELS:
        raise SecurityError("dependency provenanceLevel is invalid")
    if record["vulnerabilityStatus"] not in VULNERABILITY_STATUSES:
        raise SecurityError("dependency vulnerabilityStatus is invalid")


def validate_artifact_attestation(attestation: dict[str, Any]) -> None:
    for key in (
        "attestationId",
        "artifactId",
        "artifactDigest",
        "subjectRevision",
        "producerRunId",
        "builderId",
        "buildType",
        "provenanceLevel",
        "signatureStatus",
        "issuedAt",
    ):
        _required_string(attestation, key)
    _digest(attestation["artifactDigest"], "artifactDigest")
    if attestation["provenanceLevel"] not in PROVENANCE_LEVELS:
        raise SecurityError("artifact provenanceLevel is invalid")
    if attestation["signatureStatus"] not in SIGNATURE_STATUSES:
        raise SecurityError("artifact signatureStatus is invalid")
    _parse_time(attestation["issuedAt"], "issuedAt")
    materials = attestation.get("materials")
    if not isinstance(materials, list) or not materials:
        raise SecurityError("materials must be a non-empty array")
    for material in materials:
        if not isinstance(material, dict):
            raise SecurityError("each material must be an object")
        _required_string(material, "uri")
        digest = _required_string(material, "digest")
        _digest(digest, "material digest")


def verify_artifact(
    attestation: dict[str, Any],
    *,
    expected_artifact_id: str,
    expected_digest: str,
    expected_revision: str,
    expected_run_id: str,
    minimum_provenance: str,
    require_signature: bool,
) -> tuple[bool, tuple[str, ...]]:
    validate_artifact_attestation(attestation)
    if minimum_provenance not in PROVENANCE_LEVELS:
        raise SecurityError("minimum_provenance is invalid")
    reasons: list[str] = []
    for key, expected in (
        ("artifactId", expected_artifact_id),
        ("artifactDigest", expected_digest),
        ("subjectRevision", expected_revision),
        ("producerRunId", expected_run_id),
    ):
        if attestation[key] != expected:
            reasons.append(f"{key} does not match")
    if PROVENANCE_RANK[attestation["provenanceLevel"]] < PROVENANCE_RANK[minimum_provenance]:
        reasons.append("artifact provenance is below the required level")
    if require_signature and attestation["signatureStatus"] != "verified":
        reasons.append("artifact signature is not verified")
    return not reasons, tuple(reasons)


def _tool_reasons(
    request: dict[str, Any], grants: tuple[dict[str, Any], ...], now: datetime
) -> list[str]:
    reasons: list[str] = []
    for requested in request.get("requestedToolActions", []):
        if not isinstance(requested, dict):
            raise SecurityError("each requestedToolAction must be an object")
        tool = _required_string(requested, "tool")
        operation = _required_string(requested, "operation")
        resource = _required_string(requested, "resource")
        matches = [
            grant
            for grant in grants
            if grant["runId"] == request["runId"]
            and grant["tool"] == tool
            and operation in grant["operations"]
            and resource in grant["resources"]
            and not grant["revoked"]
            and now <= _parse_time(grant["expiresAt"], "expiresAt")
        ]
        if not matches:
            reasons.append(f"missing exact tool grant: {tool}:{operation}:{resource}")
    return reasons


def _credential_reasons(
    request: dict[str, Any], leases: tuple[dict[str, Any], ...], now: datetime
) -> list[str]:
    reasons: list[str] = []
    for requested in request.get("requestedCredentials", []):
        if not isinstance(requested, dict):
            raise SecurityError("each requestedCredential must be an object")
        audience = _required_string(requested, "audience")
        scopes = set(_strings(requested.get("scopes"), "requested scopes", minimum=1))
        matches = [
            lease
            for lease in leases
            if lease["runId"] == request["runId"]
            and lease["audience"] == audience
            and scopes.issubset(set(lease["scopes"]))
            and not lease["revoked"]
            and now <= _parse_time(lease["expiresAt"], "expiresAt")
        ]
        if not matches:
            reasons.append(f"missing scoped credential lease: {audience}")
    return reasons


def assess_security(
    request: dict[str, Any],
    contents: Iterable[dict[str, Any]],
    tool_grants: Iterable[dict[str, Any]],
    credential_leases: Iterable[dict[str, Any]],
    dependencies: Iterable[dict[str, Any]],
    sandbox: dict[str, Any],
    *,
    now: str,
) -> SecurityAssessment:
    """Fail-closed security preflight for one exact Agent Run."""

    for key in ("runId", "projectId", "riskTier", "minimumProvenance"):
        _required_string(request, key)
    if request["riskTier"] not in {"low", "moderate", "high", "critical"}:
        raise SecurityError("riskTier is invalid")
    if request["minimumProvenance"] not in PROVENANCE_LEVELS:
        raise SecurityError("minimumProvenance is invalid")
    for key in ("executesRetrievedContent", "externalSideEffectPossible"):
        if not isinstance(request.get(key), bool):
            raise SecurityError(f"{key} must be boolean")
    current_time = _parse_time(now, "now")
    validate_sandbox(sandbox)
    if sandbox["runId"] != request["runId"]:
        raise SecurityError("sandbox belongs to another run")
    content_items = tuple(contents)
    grants = tuple(tool_grants)
    leases = tuple(credential_leases)
    dependency_items = tuple(dependencies)
    for item in content_items:
        validate_content_descriptor(item)
    for item in grants:
        validate_tool_grant(item)
    for item in leases:
        validate_credential_lease(item)
    for item in dependency_items:
        validate_dependency(item)

    contain: list[str] = []
    blocked: list[str] = []
    review: list[str] = []
    controls: set[str] = {
        "preserve-security-telemetry",
        "bind-actions-to-run",
        "verify-output-before-trust",
    }
    untrusted = [item for item in content_items if item["trustLevel"] == "untrusted"]
    signals = {signal for item in content_items for signal in item["signals"]}
    serious = sorted(signals.intersection(SERIOUS_SIGNALS))
    contain.extend(f"serious security signal: {signal}" for signal in serious)
    if "prompt_injection" in signals:
        controls.add("treat-retrieved-instructions-as-data")
        review.append("prompt-injection signal requires bounded review")
    if any(item["containsInstructions"] for item in untrusted):
        controls.add("ignore-untrusted-authority-claims")
    if any(item["activeContent"] for item in untrusted):
        controls.add("quarantine-active-content")
        if request["executesRetrievedContent"]:
            if not (
                sandbox["ephemeral"]
                and sandbox["processIsolation"]
                and sandbox["cleanupOnExit"]
                and sandbox["secretAccess"] == "none"
                and sandbox["networkPolicy"] == "deny_all"
            ):
                blocked.append("untrusted active content lacks a sealed ephemeral sandbox")
    if request["executesRetrievedContent"] and not untrusted:
        controls.add("scan-before-execution")

    blocked.extend(_tool_reasons(request, grants, current_time))
    blocked.extend(_credential_reasons(request, leases, current_time))

    requested_hosts = set(_strings(request.get("requestedNetworkHosts", []), "requestedNetworkHosts"))
    sandbox_hosts = set(sandbox["networkHosts"])
    if sandbox["networkPolicy"] == "deny_all" and requested_hosts:
        blocked.append("network access requested from a deny-all sandbox")
    elif requested_hosts - sandbox_hosts:
        blocked.extend(
            f"network host is outside sandbox allowlist: {host}"
            for host in sorted(requested_hosts - sandbox_hosts)
        )
    granted_hosts = {host for grant in grants for host in grant["networkHosts"]}
    if requested_hosts - granted_hosts:
        blocked.extend(
            f"network host lacks a tool grant: {host}"
            for host in sorted(requested_hosts - granted_hosts)
        )

    if leases and sandbox["secretAccess"] != "brokered":
        blocked.append("credential use requires brokered sandbox secret access")
    if sandbox["secretAccess"] == "direct":
        blocked.append("direct secret access is prohibited")

    for dependency in dependency_items:
        label = f"{dependency['name']}@{dependency['version']}"
        if dependency["status"] != "approved":
            blocked.append(f"dependency is {dependency['status']}: {label}")
        if dependency["vulnerabilityStatus"] == "blocked":
            blocked.append(f"dependency has blocking vulnerabilities: {label}")
        elif dependency["vulnerabilityStatus"] == "unknown":
            review.append(f"dependency vulnerability status is unknown: {label}")
        if PROVENANCE_RANK[dependency["provenanceLevel"]] < PROVENANCE_RANK[request["minimumProvenance"]]:
            blocked.append(f"dependency provenance is below minimum: {label}")
        if request["riskTier"] in {"high", "critical"} and dependency["signatureStatus"] != "verified":
            blocked.append(f"high-risk dependency signature is not verified: {label}")

    if request["riskTier"] in {"high", "critical"}:
        controls.update({"independent-security-review", "signed-provenance"})
        if not sandbox["telemetry"]:
            blocked.append("high-risk execution requires security telemetry")
    if untrusted:
        controls.update({"isolate-untrusted-input", "no-authority-from-content"})
        if not sandbox["ephemeral"] or not sandbox["processIsolation"]:
            blocked.append("untrusted input requires ephemeral process isolation")

    if contain:
        decision = SecurityDecision.CONTAIN
        reasons = contain + blocked + review
    elif blocked:
        decision = SecurityDecision.BLOCK
        reasons = blocked + review
    elif review:
        decision = SecurityDecision.REVIEW_REQUIRED
        reasons = review
    elif untrusted:
        decision = SecurityDecision.ALLOW_ISOLATED
        reasons = ["untrusted input is bounded by isolation and least privilege"]
    else:
        decision = SecurityDecision.ALLOW
        reasons = ["security preflight satisfied"]
    return SecurityAssessment(
        decision,
        request["runId"],
        tuple(dict.fromkeys(reasons)),
        tuple(sorted(controls)),
    )


def build_containment_plan(
    assessment: SecurityAssessment,
    *,
    incident_id: str,
    project_id: str,
    severity: str,
    generated_at: str,
) -> dict[str, Any]:
    if assessment.decision is not SecurityDecision.CONTAIN:
        raise SecurityError("containment plan requires a contain decision")
    if severity not in {"medium", "high", "critical"}:
        raise SecurityError("containment severity must be medium, high, or critical")
    _parse_time(generated_at, "generatedAt")
    if not incident_id.strip() or not project_id.strip():
        raise SecurityError("incident and project identities are required")
    actions = [
        "revoke-run-tool-grants",
        "revoke-run-credential-leases",
        "isolate-network",
        "freeze-run-workspace",
        "quarantine-run-artifacts",
        "preserve-events-and-telemetry",
        "open-security-finding",
    ]
    if severity in {"high", "critical"}:
        actions.append("notify-security-owner")
    if severity == "critical":
        actions.extend(["pause-affected-project", "rotate-exposed-credentials"])
    plan = {
        "schemaVersion": "0.1",
        "incidentId": incident_id,
        "projectId": project_id,
        "runId": assessment.run_id,
        "severity": severity,
        "generatedAt": generated_at,
        "reasons": list(assessment.reasons),
        "actions": actions,
    }
    plan["planDigest"] = canonical_digest(plan)
    return plan


def validate_containment_plan(plan: dict[str, Any]) -> None:
    for key in (
        "schemaVersion",
        "incidentId",
        "projectId",
        "runId",
        "severity",
        "generatedAt",
        "planDigest",
    ):
        _required_string(plan, key)
    if plan["severity"] not in {"medium", "high", "critical"}:
        raise SecurityError("containment severity is invalid")
    _parse_time(plan["generatedAt"], "generatedAt")
    _strings(plan.get("reasons"), "reasons", minimum=1)
    _strings(plan.get("actions"), "actions", minimum=1)
    unsigned = dict(plan)
    supplied = unsigned.pop("planDigest")
    _digest(supplied, "planDigest")
    if canonical_digest(unsigned) != supplied:
        raise SecurityError("containment plan digest does not match content")
