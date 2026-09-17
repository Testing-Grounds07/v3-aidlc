"""Validated handoffs between a user-facing liaison and the V3 Project Lead."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class GatewayError(ValueError):
    """Raised when a gateway contract or message violates the protocol."""


class Actor(str, Enum):
    USER = "user"
    LIAISON = "liaison"
    PROJECT_LEAD = "project_lead"


class ActivationDecision(str, Enum):
    STAY_CONVERSATIONAL = "stay_conversational"
    START_MANAGED_INTAKE = "start_managed_intake"
    ATTACH_EXISTING_PROJECT = "attach_existing_project"
    CLARIFY_PROJECT_IDENTITY = "clarify_project_identity"


class MessageKind(str, Enum):
    USER_REQUEST = "user_request"
    INTAKE_PROPOSAL = "intake_proposal"
    CLARIFICATION_NEEDED = "clarification_needed"
    CLARIFICATION_REQUEST = "clarification_request"
    USER_CLARIFICATION = "user_clarification"
    CLARIFICATION_SUBMISSION = "clarification_submission"
    PROGRESS = "progress"
    PROGRESS_UPDATE = "progress_update"
    DECISION_NEEDED = "decision_needed"
    DECISION_REQUEST = "decision_request"
    USER_DECISION = "user_decision"
    DECISION_SUBMISSION = "decision_submission"
    DECISION_RECORDED = "decision_recorded"
    BLOCKED = "blocked"
    BLOCKED_NOTICE = "blocked_notice"
    COMPLETED = "completed"
    COMPLETION_REPORT = "completion_report"
    CORRECTION = "correction"
    CORRECTION_SUBMISSION = "correction_submission"
    DELEGATION = "delegation"
    DELEGATION_PROPOSAL = "delegation_proposal"
    REVOCATION = "revocation"
    REVOCATION_SUBMISSION = "revocation_submission"


ALLOWED_DIRECTIONS = {
    MessageKind.USER_REQUEST: (Actor.USER, Actor.LIAISON),
    MessageKind.INTAKE_PROPOSAL: (Actor.LIAISON, Actor.PROJECT_LEAD),
    MessageKind.CLARIFICATION_NEEDED: (Actor.PROJECT_LEAD, Actor.LIAISON),
    MessageKind.CLARIFICATION_REQUEST: (Actor.LIAISON, Actor.USER),
    MessageKind.USER_CLARIFICATION: (Actor.USER, Actor.LIAISON),
    MessageKind.CLARIFICATION_SUBMISSION: (Actor.LIAISON, Actor.PROJECT_LEAD),
    MessageKind.PROGRESS: (Actor.PROJECT_LEAD, Actor.LIAISON),
    MessageKind.PROGRESS_UPDATE: (Actor.LIAISON, Actor.USER),
    MessageKind.DECISION_NEEDED: (Actor.PROJECT_LEAD, Actor.LIAISON),
    MessageKind.DECISION_REQUEST: (Actor.LIAISON, Actor.USER),
    MessageKind.USER_DECISION: (Actor.USER, Actor.LIAISON),
    MessageKind.DECISION_SUBMISSION: (Actor.LIAISON, Actor.PROJECT_LEAD),
    MessageKind.DECISION_RECORDED: (Actor.PROJECT_LEAD, Actor.LIAISON),
    MessageKind.BLOCKED: (Actor.PROJECT_LEAD, Actor.LIAISON),
    MessageKind.BLOCKED_NOTICE: (Actor.LIAISON, Actor.USER),
    MessageKind.COMPLETED: (Actor.PROJECT_LEAD, Actor.LIAISON),
    MessageKind.COMPLETION_REPORT: (Actor.LIAISON, Actor.USER),
    MessageKind.CORRECTION: (Actor.USER, Actor.LIAISON),
    MessageKind.CORRECTION_SUBMISSION: (Actor.LIAISON, Actor.PROJECT_LEAD),
    MessageKind.DELEGATION: (Actor.USER, Actor.LIAISON),
    MessageKind.DELEGATION_PROPOSAL: (Actor.LIAISON, Actor.PROJECT_LEAD),
    MessageKind.REVOCATION: (Actor.USER, Actor.LIAISON),
    MessageKind.REVOCATION_SUBMISSION: (Actor.LIAISON, Actor.PROJECT_LEAD),
}


RELAY_PAIRS = {
    MessageKind.USER_REQUEST: MessageKind.INTAKE_PROPOSAL,
    MessageKind.CLARIFICATION_NEEDED: MessageKind.CLARIFICATION_REQUEST,
    MessageKind.USER_CLARIFICATION: MessageKind.CLARIFICATION_SUBMISSION,
    MessageKind.PROGRESS: MessageKind.PROGRESS_UPDATE,
    MessageKind.DECISION_NEEDED: MessageKind.DECISION_REQUEST,
    MessageKind.USER_DECISION: MessageKind.DECISION_SUBMISSION,
    MessageKind.BLOCKED: MessageKind.BLOCKED_NOTICE,
    MessageKind.COMPLETED: MessageKind.COMPLETION_REPORT,
    MessageKind.CORRECTION: MessageKind.CORRECTION_SUBMISSION,
    MessageKind.DELEGATION: MessageKind.DELEGATION_PROPOSAL,
    MessageKind.REVOCATION: MessageKind.REVOCATION_SUBMISSION,
}


REQUIRED_PAYLOAD_FIELDS = {
    MessageKind.USER_REQUEST: {"verbatimRequest"},
    MessageKind.INTAKE_PROPOSAL: {
        "verbatimRequest",
        "requestedOutcome",
        "constraints",
        "assumptions",
    },
    MessageKind.CLARIFICATION_NEEDED: {"question", "reason"},
    MessageKind.USER_CLARIFICATION: {"answer"},
    MessageKind.CLARIFICATION_SUBMISSION: {"answer"},
    MessageKind.PROGRESS: {"summary", "completed", "next"},
    MessageKind.DECISION_NEEDED: {"question", "options", "impact"},
    MessageKind.USER_DECISION: {"selectedOption", "verbatimResponse"},
    MessageKind.DECISION_SUBMISSION: {"selectedOption", "verbatimResponse"},
    MessageKind.DECISION_RECORDED: {"decisionId", "eventIds"},
    MessageKind.BLOCKED: {"reason", "affectedWork", "canContinue"},
    MessageKind.COMPLETED: {"outcome", "evidence", "remainingWork"},
    MessageKind.CORRECTION: {"verbatimCorrection"},
    MessageKind.CORRECTION_SUBMISSION: {"verbatimCorrection"},
    MessageKind.DELEGATION: {"verbatimDelegation"},
    MessageKind.DELEGATION_PROPOSAL: {"verbatimDelegation", "normalizedScope"},
    MessageKind.REVOCATION: {"verbatimRevocation"},
    MessageKind.REVOCATION_SUBMISSION: {"verbatimRevocation"},
}


USER_DIRECTED = {
    MessageKind.CLARIFICATION_REQUEST,
    MessageKind.PROGRESS_UPDATE,
    MessageKind.DECISION_REQUEST,
    MessageKind.BLOCKED_NOTICE,
    MessageKind.COMPLETION_REPORT,
}


USER_MESSAGE_FIELDS = {"headline", "explanation", "impact", "actionNeeded"}
INTERNAL_ID_PATTERN = re.compile(
    r"\b(?:PRJ|POL|RULE|CTRL|MODE|ROUTE|BOLT|UNIT|WS|EVT|DEC|V3\.1)-[A-Z0-9.-]+\b"
)
INTERNAL_JARGON = {
    "bolt",
    "work package",
    "route instance",
    "posture",
    "canonical state",
    "policy predicate",
}


@dataclass(frozen=True)
class ActivationResult:
    decision: ActivationDecision
    reasons: tuple[str, ...]


def decide_activation(facts: dict[str, Any]) -> ActivationResult:
    """Choose whether ordinary conversation should enter managed V3 work."""

    if facts.get("projectIdentityAmbiguous") is True:
        return ActivationResult(
            ActivationDecision.CLARIFY_PROJECT_IDENTITY,
            ("More than one project could own this work.",),
        )
    if facts.get("existingProjectRef"):
        return ActivationResult(
            ActivationDecision.ATTACH_EXISTING_PROJECT,
            ("The request identifies an existing managed project.",),
        )

    reasons = []
    signals = {
        "explicitFrameworkRequest": "The user explicitly requested managed framework work.",
        "needsPersistentState": "The work must continue reliably across sessions.",
        "needsOrchestration": "The work needs coordinated stages or parallel work.",
        "hasExternalSideEffects": "The work may create governed external effects.",
    }
    for fact, reason in signals.items():
        if facts.get(fact) is True:
            reasons.append(reason)
    if facts.get("multiStep") is True and facts.get("createsDurableArtifact") is True:
        reasons.append("The request is multi-step and creates a durable artifact.")

    if reasons:
        return ActivationResult(
            ActivationDecision.START_MANAGED_INTAKE, tuple(reasons)
        )
    return ActivationResult(
        ActivationDecision.STAY_CONVERSATIONAL,
        ("The request can be handled as a simple, self-contained conversation.",),
    )


def load_protocol(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GatewayError(f"Cannot load protocol {path}: {error}") from error
    if not isinstance(value, dict):
        raise GatewayError("Protocol must contain a JSON object")
    return value


def validate_protocol(protocol: dict[str, Any]) -> None:
    for key in ("id", "version", "title"):
        if not isinstance(protocol.get(key), str) or not protocol[key].strip():
            raise GatewayError(f"{key} must be a non-empty string")
    actors = protocol.get("actors")
    if not isinstance(actors, list) or set(actors) != {actor.value for actor in Actor}:
        raise GatewayError("actors must contain user, liaison, and project_lead")
    kinds = protocol.get("messageKinds")
    if not isinstance(kinds, list) or set(kinds) != {
        kind.value for kind in MessageKind
    }:
        raise GatewayError("messageKinds do not match the executable protocol")
    if protocol.get("canonicalWriter") != Actor.PROJECT_LEAD.value:
        raise GatewayError("The Project Lead must remain the canonical writer")
    if protocol.get("userLanguage") != "plain":
        raise GatewayError("User-facing language must be plain")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_envelope(envelope: dict[str, Any]) -> None:
    required = {
        "schemaVersion",
        "messageId",
        "conversationId",
        "kind",
        "sender",
        "recipient",
        "createdAt",
        "payload",
    }
    missing = required - envelope.keys()
    if missing:
        raise GatewayError(f"Envelope is missing fields: {sorted(missing)}")
    for key in ("messageId", "conversationId", "createdAt"):
        if not _nonempty_string(envelope[key]):
            raise GatewayError(f"{key} must be a non-empty string")
    try:
        kind = MessageKind(envelope["kind"])
        sender = Actor(envelope["sender"])
        recipient = Actor(envelope["recipient"])
    except ValueError as error:
        raise GatewayError("Envelope contains an unknown kind or actor") from error
    if (sender, recipient) != ALLOWED_DIRECTIONS[kind]:
        raise GatewayError(f"{kind.value} has an invalid sender or recipient")
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise GatewayError("payload must be an object")
    missing_payload = REQUIRED_PAYLOAD_FIELDS.get(kind, set()) - payload.keys()
    if missing_payload:
        raise GatewayError(
            f"{kind.value} payload is missing fields: {sorted(missing_payload)}"
        )

    if sender is Actor.LIAISON and recipient is Actor.PROJECT_LEAD:
        prohibited = {"eventIds", "decisionId", "recorded", "canonicalStatus"}
        present = prohibited.intersection(payload)
        if present:
            raise GatewayError(
                f"Liaison proposals cannot claim canonical fields: {sorted(present)}"
            )
    if kind in USER_DIRECTED:
        validate_user_message(payload, kind)


def validate_user_message(payload: dict[str, Any], kind: MessageKind) -> None:
    missing = USER_MESSAGE_FIELDS - payload.keys()
    if missing:
        raise GatewayError(
            f"User-facing message is missing fields: {sorted(missing)}"
        )
    primary_text = []
    for key in USER_MESSAGE_FIELDS:
        value = payload[key]
        if not _nonempty_string(value):
            raise GatewayError(f"User-facing {key} must be a non-empty string")
        primary_text.append(value)
    combined = " ".join(primary_text)
    if INTERNAL_ID_PATTERN.search(combined):
        raise GatewayError("Internal IDs must not appear in primary user-facing text")
    lowered = combined.lower()
    used_jargon = sorted(term for term in INTERNAL_JARGON if term in lowered)
    if used_jargon:
        raise GatewayError(
            f"Unexplained framework jargon in user-facing text: {used_jargon}"
        )

    if kind is MessageKind.DECISION_REQUEST:
        options = payload.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 4:
            raise GatewayError("A decision request must provide two to four options")
        for option in options:
            if not isinstance(option, dict) or not all(
                _nonempty_string(option.get(key)) for key in ("id", "label", "tradeoff")
            ):
                raise GatewayError("Each decision option needs id, label, and tradeoff")
        if payload.get("recommendationSupported") is True and not _nonempty_string(
            payload.get("recommendation")
        ):
            raise GatewayError(
                "An evidence-supported decision request must include a recommendation"
            )


def validate_relay(source: dict[str, Any], relay: dict[str, Any]) -> None:
    """Verify that a liaison handoff is the permitted counterpart to its source."""

    validate_envelope(source)
    validate_envelope(relay)
    source_kind = MessageKind(source["kind"])
    relay_kind = MessageKind(relay["kind"])
    expected = RELAY_PAIRS.get(source_kind)
    if expected is None or relay_kind is not expected:
        raise GatewayError(
            f"{source_kind.value} cannot be relayed as {relay_kind.value}"
        )
    if relay.get("correlationId") != source["messageId"]:
        raise GatewayError("Relay must correlate to its source message")
    if relay["conversationId"] != source["conversationId"]:
        raise GatewayError("Relay must remain in the same conversation")
    if "verbatimRequest" in source["payload"] and relay["payload"].get(
        "verbatimRequest"
    ) != source["payload"]["verbatimRequest"]:
        raise GatewayError("The user's verbatim request must be preserved")
    if source_kind is MessageKind.DECISION_NEEDED:
        source_options = source["payload"].get("options")
        relay_options = relay["payload"].get("options")
        if not isinstance(source_options, list) or not isinstance(relay_options, list):
            raise GatewayError("Decision options must be arrays")
        source_ids = [item.get("id") for item in source_options if isinstance(item, dict)]
        relay_ids = [item.get("id") for item in relay_options if isinstance(item, dict)]
        if source_ids != relay_ids:
            raise GatewayError("A decision relay must preserve option IDs and order")
    for verbatim_field in (
        "verbatimResponse",
        "verbatimCorrection",
        "verbatimDelegation",
        "verbatimRevocation",
    ):
        if verbatim_field in source["payload"] and relay["payload"].get(
            verbatim_field
        ) != source["payload"][verbatim_field]:
            raise GatewayError(f"{verbatim_field} must be preserved")


def validate_transcript(envelopes: Iterable[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for envelope in envelopes:
        validate_envelope(envelope)
        message_id = envelope["messageId"]
        if message_id in seen:
            raise GatewayError(f"Duplicate message ID: {message_id}")
        seen.add(message_id)
        correlation = envelope.get("correlationId")
        if correlation is not None and correlation not in seen:
            raise GatewayError(
                f"Correlation must reference an earlier message: {correlation}"
            )
