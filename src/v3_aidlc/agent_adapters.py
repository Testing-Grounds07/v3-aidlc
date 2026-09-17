"""Provider-neutral capability negotiation and Agent Run contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable, Protocol


class AdapterError(ValueError):
    """Raised when an adapter contract cannot be trusted or satisfied."""


class NegotiationDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


SENSITIVITY_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
    "secret": 4,
}
AUTO_AUTHORIZATION = {
    "auto_proceed",
    "auto_proceed_and_record",
    "auto_proceed_within_budget",
}
TERMINAL_RUN_STATUSES = {item.value for item in RunStatus}


@dataclass(frozen=True)
class NegotiationResult:
    decision: NegotiationDecision
    adapter_id: str
    profile_digest: str
    reasons: tuple[str, ...]


class AgentAdapter(Protocol):
    """Boundary implemented by provider-specific integrations."""

    def capability_profile(self) -> dict[str, Any]: ...

    def invoke(self, dispatch: dict[str, Any]) -> dict[str, Any]: ...


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise AdapterError(f"{key} must be a non-empty string")
    return result


def _string_array(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise AdapterError(f"{key} must be a string array")
    if len(value) != len(set(value)):
        raise AdapterError(f"{key} contains duplicates")
    return tuple(value)


def _positive_integer(value: dict[str, Any], key: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or isinstance(result, bool) or result < 1:
        raise AdapterError(f"{key} must be a positive integer")
    return result


def canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_time(value: Any, key: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"{key} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AdapterError(f"{key} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise AdapterError(f"{key} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_capability_profile(profile: dict[str, Any]) -> None:
    for key in (
        "schemaVersion",
        "profileId",
        "adapterId",
        "adapterVersion",
        "provider",
        "model",
    ):
        _required_string(profile, key)
    if profile.get("status") not in {"available", "degraded", "unavailable"}:
        raise AdapterError("status must be available, degraded, or unavailable")
    for key in ("roles", "capabilities", "modalities", "tools", "networkHosts"):
        _string_array(profile.get(key), key)
    for key in ("maxContextBytes", "maxOutputBytes", "maxConcurrentRuns"):
        _positive_integer(profile, key)
    if profile.get("maxSensitivity") not in SENSITIVITY_RANK:
        raise AdapterError("maxSensitivity is invalid")
    for key in (
        "structuredOutput",
        "streaming",
        "externalSideEffects",
        "idempotentInvocation",
    ):
        if not isinstance(profile.get(key), bool):
            raise AdapterError(f"{key} must be boolean")


def validate_run_request(request: dict[str, Any]) -> None:
    for key in (
        "schemaVersion",
        "runId",
        "projectId",
        "workPackageId",
        "role",
        "objective",
        "contextManifestId",
        "contextManifestDigest",
        "authorizationDecision",
        "idempotencyKey",
    ):
        _required_string(request, key)
    for key in (
        "requiredCapabilities",
        "requiredModalities",
        "requiredTools",
        "requiredNetworkHosts",
        "completionCriteria",
    ):
        _string_array(request.get(key), key)
    _positive_integer(request, "contextBytes")
    _positive_integer(request, "maxOutputBytes")
    _positive_integer(request, "attempt")
    if request.get("sensitivity") not in SENSITIVITY_RANK:
        raise AdapterError("sensitivity is invalid")
    for key in ("structuredOutputRequired", "externalSideEffectPossible"):
        if not isinstance(request.get(key), bool):
            raise AdapterError(f"{key} must be boolean")


def negotiate_capabilities(
    request: dict[str, Any], profile: dict[str, Any]
) -> NegotiationResult:
    """Compare one exact run request with one immutable capability profile."""

    validate_run_request(request)
    validate_capability_profile(profile)
    reasons: list[str] = []

    if profile["status"] != "available":
        reasons.append(f"runner status is {profile['status']}")
    if request["authorizationDecision"] not in AUTO_AUTHORIZATION:
        reasons.append(
            f"authorization decision {request['authorizationDecision']} does not permit dispatch"
        )
    if request["role"] not in profile["roles"]:
        reasons.append(f"role {request['role']} is unsupported")

    for request_key, profile_key, label in (
        ("requiredCapabilities", "capabilities", "capability"),
        ("requiredModalities", "modalities", "modality"),
        ("requiredTools", "tools", "tool"),
        ("requiredNetworkHosts", "networkHosts", "network host"),
    ):
        missing = sorted(set(request[request_key]) - set(profile[profile_key]))
        reasons.extend(f"missing {label}: {item}" for item in missing)

    if request["contextBytes"] > profile["maxContextBytes"]:
        reasons.append("context exceeds runner limit")
    if request["maxOutputBytes"] > profile["maxOutputBytes"]:
        reasons.append("requested output exceeds runner limit")
    if (
        SENSITIVITY_RANK[request["sensitivity"]]
        > SENSITIVITY_RANK[profile["maxSensitivity"]]
    ):
        reasons.append("context sensitivity exceeds runner clearance")
    if request["structuredOutputRequired"] and not profile["structuredOutput"]:
        reasons.append("structured output is required but unsupported")
    if request["externalSideEffectPossible"] and not profile["externalSideEffects"]:
        reasons.append("external side effects are required but unsupported")
    if request["attempt"] > 1 and not profile["idempotentInvocation"]:
        reasons.append("retry requires idempotent invocation support")

    return NegotiationResult(
        decision=(
            NegotiationDecision.REJECTED if reasons else NegotiationDecision.ACCEPTED
        ),
        adapter_id=profile["adapterId"],
        profile_digest=canonical_digest(profile),
        reasons=tuple(reasons),
    )


def select_adapter(
    request: dict[str, Any], profiles: Iterable[dict[str, Any]]
) -> tuple[dict[str, Any], tuple[NegotiationResult, ...]]:
    """Choose deterministically among sufficient runners; never guess capabilities."""

    results: list[tuple[dict[str, Any], NegotiationResult]] = []
    seen: set[str] = set()
    for profile in profiles:
        validate_capability_profile(profile)
        adapter_id = profile["adapterId"]
        if adapter_id in seen:
            raise AdapterError(f"duplicate adapterId: {adapter_id}")
        seen.add(adapter_id)
        results.append((profile, negotiate_capabilities(request, profile)))
    if not results:
        raise AdapterError("at least one capability profile is required")

    accepted = [item for item in results if item[1].decision is NegotiationDecision.ACCEPTED]
    if not accepted:
        details = "; ".join(
            f"{result.adapter_id}: {', '.join(result.reasons)}"
            for _, result in sorted(results, key=lambda item: item[1].adapter_id)
        )
        raise AdapterError(f"no compatible adapter: {details}")

    # Prefer the least excess clearance and capacity, then a stable adapter ID.
    accepted.sort(
        key=lambda item: (
            SENSITIVITY_RANK[item[0]["maxSensitivity"]]
            - SENSITIVITY_RANK[request["sensitivity"]],
            item[0]["maxContextBytes"] - request["contextBytes"],
            item[0]["maxOutputBytes"] - request["maxOutputBytes"],
            item[0]["adapterId"],
        )
    )
    return accepted[0][0], tuple(item[1] for item in results)


def build_dispatch(
    request: dict[str, Any],
    profile: dict[str, Any],
    *,
    lease_id: str,
) -> dict[str, Any]:
    result = negotiate_capabilities(request, profile)
    if result.decision is not NegotiationDecision.ACCEPTED:
        raise AdapterError("cannot dispatch an incompatible runner: " + "; ".join(result.reasons))
    if not lease_id.strip():
        raise AdapterError("lease_id must be a non-empty string")
    dispatch = {
        "schemaVersion": "0.1",
        "runId": request["runId"],
        "projectId": request["projectId"],
        "workPackageId": request["workPackageId"],
        "adapterId": profile["adapterId"],
        "adapterVersion": profile["adapterVersion"],
        "profileId": profile["profileId"],
        "profileDigest": result.profile_digest,
        "contextManifestId": request["contextManifestId"],
        "contextManifestDigest": request["contextManifestDigest"],
        "leaseId": lease_id,
        "attempt": request["attempt"],
        "idempotencyKey": request["idempotencyKey"],
        "requestDigest": canonical_digest(request),
        "request": request,
    }
    dispatch["dispatchDigest"] = canonical_digest(dispatch)
    return dispatch


def validate_dispatch(dispatch: dict[str, Any]) -> None:
    for key in (
        "schemaVersion",
        "runId",
        "projectId",
        "workPackageId",
        "adapterId",
        "adapterVersion",
        "profileId",
        "profileDigest",
        "contextManifestId",
        "contextManifestDigest",
        "leaseId",
        "idempotencyKey",
        "requestDigest",
        "dispatchDigest",
    ):
        _required_string(dispatch, key)
    _positive_integer(dispatch, "attempt")
    request = dispatch.get("request")
    if not isinstance(request, dict):
        raise AdapterError("dispatch request must be an object")
    validate_run_request(request)
    if canonical_digest(request) != dispatch["requestDigest"]:
        raise AdapterError("dispatch request digest does not match request")
    for key in (
        "runId",
        "projectId",
        "workPackageId",
        "contextManifestId",
        "contextManifestDigest",
        "attempt",
        "idempotencyKey",
    ):
        if dispatch[key] != request[key]:
            raise AdapterError(f"dispatch {key} does not match request")
    unsigned = dict(dispatch)
    supplied_digest = unsigned.pop("dispatchDigest")
    if canonical_digest(unsigned) != supplied_digest:
        raise AdapterError("dispatch digest does not match content")


def validate_run_result(result: dict[str, Any], dispatch: dict[str, Any]) -> None:
    validate_dispatch(dispatch)
    for key in (
        "schemaVersion",
        "runId",
        "projectId",
        "workPackageId",
        "adapterId",
        "profileDigest",
        "contextManifestId",
        "dispatchDigest",
        "startedAt",
        "finishedAt",
        "status",
        "summary",
    ):
        _required_string(result, key)
    started = _parse_time(result["startedAt"], "startedAt")
    finished = _parse_time(result["finishedAt"], "finishedAt")
    if finished < started:
        raise AdapterError("finishedAt cannot be earlier than startedAt")
    if result["status"] not in TERMINAL_RUN_STATUSES:
        raise AdapterError("result status is invalid")
    for key in ("artifactIds", "evidenceIds", "satisfiedCriteria", "findingIds"):
        _string_array(result.get(key), key)
    usage = result.get("usage")
    if not isinstance(usage, dict):
        raise AdapterError("usage must be an object")
    for key in ("inputUnits", "outputUnits"):
        value = usage.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise AdapterError(f"usage.{key} must be a non-negative integer")

    exact_matches = (
        ("runId", "runId"),
        ("projectId", "projectId"),
        ("workPackageId", "workPackageId"),
        ("adapterId", "adapterId"),
        ("profileDigest", "profileDigest"),
        ("contextManifestId", "contextManifestId"),
        ("dispatchDigest", "dispatchDigest"),
    )
    for result_key, dispatch_key in exact_matches:
        if result[result_key] != dispatch[dispatch_key]:
            raise AdapterError(f"result {result_key} does not match dispatch")

    effects = result.get("externalEffects", [])
    if not isinstance(effects, list):
        raise AdapterError("externalEffects must be an array")
    if effects and not dispatch["request"]["externalSideEffectPossible"]:
        raise AdapterError("runner reported an external effect that was not authorized")
    for effect in effects:
        if not isinstance(effect, dict):
            raise AdapterError("each external effect must be an object")
        for key in ("effectKey", "effectType", "status", "observationRef"):
            _required_string(effect, key)
        if effect["status"] not in {"succeeded", "absent", "unknown"}:
            raise AdapterError("external effect status is invalid")

    if result["status"] == RunStatus.COMPLETED:
        required = set(dispatch["request"]["completionCriteria"])
        satisfied = set(result["satisfiedCriteria"])
        missing = sorted(required - satisfied)
        if missing:
            raise AdapterError("completed result is missing criteria: " + ", ".join(missing))
        if required and not result["evidenceIds"]:
            raise AdapterError("completed result requires evidence")
    elif result["satisfiedCriteria"]:
        raise AdapterError("non-completed result cannot claim satisfied criteria")


def normalize_provider_result(
    raw_result: dict[str, Any],
    dispatch: dict[str, Any],
    *,
    provider_result_ref: str,
) -> dict[str, Any]:
    """Normalize adapter output without placing opaque provider payloads in state."""

    if not provider_result_ref.strip():
        raise AdapterError("provider_result_ref must be a non-empty string")
    if not isinstance(raw_result, dict):
        raise AdapterError("raw provider result must be an object")
    result = {
        "schemaVersion": "0.1",
        "runId": dispatch["runId"],
        "projectId": dispatch["projectId"],
        "workPackageId": dispatch["workPackageId"],
        "adapterId": dispatch["adapterId"],
        "profileDigest": dispatch["profileDigest"],
        "contextManifestId": dispatch["contextManifestId"],
        "dispatchDigest": dispatch["dispatchDigest"],
        "startedAt": raw_result.get("startedAt"),
        "finishedAt": raw_result.get("finishedAt"),
        "status": raw_result.get("status"),
        "summary": raw_result.get("summary"),
        "artifactIds": raw_result.get("artifactIds", []),
        "evidenceIds": raw_result.get("evidenceIds", []),
        "satisfiedCriteria": raw_result.get("satisfiedCriteria", []),
        "findingIds": raw_result.get("findingIds", []),
        "externalEffects": raw_result.get("externalEffects", []),
        "usage": raw_result.get("usage", {"inputUnits": 0, "outputUnits": 0}),
        "providerResultRef": provider_result_ref,
    }
    validate_run_result(result, dispatch)
    return result
