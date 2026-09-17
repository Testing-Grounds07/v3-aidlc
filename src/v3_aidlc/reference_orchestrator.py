"""Executable reference assembly of the V3-AIDLC architecture contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .agent_adapters import (
    AdapterError,
    AgentAdapter,
    build_dispatch,
    normalize_provider_result,
    select_adapter,
)
from .authorization import AuthorizationDecision, evaluate_authorization
from .context_compiler import ContextError, compile_context
from .conversational_gateway import ActivationDecision, decide_activation
from .evidence_gates import GateOutcome, evaluate_gate
from .lifecycle_contracts import select_modes
from .recovery import append_event, plan_recovery
from .recovery import verify_event_chain
from .scheduler import (
    ScheduleDecision,
    build_integration_batch,
    schedule,
    schedule_plan_to_dict,
    validate_integration_result,
)


class OrchestratorError(ValueError):
    """Raised when a conformance scenario is malformed or internally inconsistent."""


@dataclass(frozen=True)
class WorkTrace:
    work_package_id: str
    authorization: str
    authorization_explanation: str
    context_manifest_id: str | None
    adapter_id: str | None
    schedule_decision: str
    run_status: str | None
    gate_outcome: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OrchestrationTrace:
    scenario_id: str
    project_id: str
    status: str
    activation: str
    route_id: str
    stage: str
    mode_ids: tuple[str, ...]
    state_revision: str
    work: tuple[WorkTrace, ...]
    schedule_plan: dict[str, Any] | None
    integration_batch: dict[str, Any] | None
    integration_status: str | None
    events: tuple[dict[str, Any], ...]
    summary: str


TRACE_STATUSES = {
    "not_managed",
    "completed",
    "waiting",
    "decision_required",
    "blocked",
    "failed",
}


def validate_trace(trace: OrchestrationTrace) -> None:
    if trace.status not in TRACE_STATUSES:
        raise OrchestratorError("trace status is invalid")
    for key, value in (
        ("scenario_id", trace.scenario_id),
        ("project_id", trace.project_id),
        ("route_id", trace.route_id),
        ("stage", trace.stage),
        ("state_revision", trace.state_revision),
        ("summary", trace.summary),
    ):
        if not isinstance(value, str) or not value.strip():
            raise OrchestratorError(f"trace {key} must be a non-empty string")
    work_ids = [item.work_package_id for item in trace.work]
    if len(work_ids) != len(set(work_ids)):
        raise OrchestratorError("trace work-package identities must be unique")
    if trace.status == "not_managed":
        if trace.events or trace.schedule_plan or trace.integration_batch:
            raise OrchestratorError("unmanaged trace cannot claim managed execution")
        return
    if not trace.events:
        raise OrchestratorError("managed trace requires durable events")
    verify_event_chain(trace.events)
    if any(event["projectId"] != trace.project_id for event in trace.events):
        raise OrchestratorError("trace events belong to another project")
    if trace.schedule_plan is not None:
        selected = set(trace.schedule_plan["selectedWorkPackageIds"])
        traced_selected = {
            item.work_package_id
            for item in trace.work
            if item.schedule_decision == "selected"
        }
        if selected != traced_selected:
            raise OrchestratorError("trace schedule does not match work decisions")
    if trace.integration_status == "passed" and trace.integration_batch is None:
        raise OrchestratorError("passed integration requires its batch")


def trace_to_dict(trace: OrchestrationTrace) -> dict[str, Any]:
    validate_trace(trace)
    return {
        "schemaVersion": "0.1",
        "scenarioId": trace.scenario_id,
        "projectId": trace.project_id,
        "status": trace.status,
        "activation": trace.activation,
        "routeId": trace.route_id,
        "stage": trace.stage,
        "modeIds": list(trace.mode_ids),
        "stateRevision": trace.state_revision,
        "work": [
            {
                "workPackageId": item.work_package_id,
                "authorization": item.authorization,
                "authorizationExplanation": item.authorization_explanation,
                "contextManifestId": item.context_manifest_id,
                "adapterId": item.adapter_id,
                "scheduleDecision": item.schedule_decision,
                "runStatus": item.run_status,
                "gateOutcome": item.gate_outcome,
                "reasons": list(item.reasons),
            }
            for item in trace.work
        ],
        "schedulePlan": trace.schedule_plan,
        "integrationBatch": trace.integration_batch,
        "integrationStatus": trace.integration_status,
        "events": list(trace.events),
        "summary": trace.summary,
    }


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise OrchestratorError(f"{key} must be a non-empty string")
    return result


def _event_draft(
    *,
    number: int,
    project_id: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
    occurred_at: str,
    correlation_id: str,
    causation_id: str | None,
) -> dict[str, Any]:
    event = {
        "schemaVersion": "0.1",
        "eventId": f"TRACE-EVT-{number:04d}",
        "projectId": project_id,
        "streamId": f"project:{project_id}",
        "eventType": event_type,
        "aggregateType": aggregate_type,
        "aggregateId": aggregate_id,
        "occurredAt": occurred_at,
        "recordedAt": occurred_at,
        "actor": {"type": "project_lead", "id": "reference-project-lead"},
        "idempotencyKey": f"{correlation_id}:{number}:{event_type}:{aggregate_id}",
        "correlationId": correlation_id,
        "payload": payload,
    }
    if causation_id:
        event["causationId"] = causation_id
    return event


class ReferenceOrchestrator:
    """A deterministic conformance runtime, not a production execution service."""

    def __init__(self, adapters: Iterable[AgentAdapter]):
        self._adapters: dict[str, AgentAdapter] = {}
        for adapter in adapters:
            profile = adapter.capability_profile()
            adapter_id = _required_string(profile, "adapterId")
            if adapter_id in self._adapters:
                raise OrchestratorError(f"duplicate adapter: {adapter_id}")
            self._adapters[adapter_id] = adapter

    def execute(self, scenario: dict[str, Any]) -> OrchestrationTrace:
        scenario_id = _required_string(scenario, "scenarioId")
        project_id = _required_string(scenario, "projectId")
        state_revision = _required_string(scenario, "stateRevision")
        now = _required_string(scenario, "now")
        stage = _required_string(scenario, "stage")
        activation = decide_activation(scenario.get("activationFacts", {}))
        if activation.decision is ActivationDecision.STAY_CONVERSATIONAL:
            trace = OrchestrationTrace(
                scenario_id,
                project_id,
                "not_managed",
                activation.decision.value,
                "none",
                stage,
                (),
                state_revision,
                (),
                None,
                None,
                None,
                (),
                "The request remains an ordinary conversation.",
            )
            validate_trace(trace)
            return trace

        route = scenario.get("route")
        mode_library = scenario.get("modeLibrary")
        if not isinstance(route, dict) or not isinstance(mode_library, dict):
            raise OrchestratorError("route and modeLibrary are required")
        selection = select_modes(
            route,
            mode_library,
            stage,
            scenario.get("routeFacts", {}),
            posture=scenario.get("posture"),
            optional_mode_ids=scenario.get("optionalModeIds", ()),
        )
        mode_ids = tuple(item.mode_id for item in selection.selected)

        policies = scenario.get("authorizationPolicies")
        recipe = scenario.get("contextRecipe")
        work_items = scenario.get("work")
        if not isinstance(policies, list) or not policies:
            raise OrchestratorError("authorizationPolicies must be a non-empty array")
        if not isinstance(recipe, dict):
            raise OrchestratorError("contextRecipe is required")
        if not isinstance(work_items, list) or not work_items:
            raise OrchestratorError("work must be a non-empty array")

        histories: tuple[dict[str, Any], ...] = ()
        event_number = 1
        last_event_id: str | None = None

        def record(
            event_type: str,
            aggregate_type: str,
            aggregate_id: str,
            payload: dict[str, Any],
        ) -> None:
            nonlocal histories, event_number, last_event_id
            histories, appended, _ = append_event(
                histories,
                _event_draft(
                    number=event_number,
                    project_id=project_id,
                    event_type=event_type,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    payload=payload,
                    occurred_at=now,
                    correlation_id=scenario_id,
                    causation_id=last_event_id,
                ),
            )
            last_event_id = appended["eventId"]
            event_number += 1

        record(
            "orchestration.started",
            "project",
            project_id,
            {"routeId": selection.route_id, "stage": stage, "modeIds": list(mode_ids)},
        )

        prepared: dict[str, dict[str, Any]] = {}
        traces: dict[str, WorkTrace] = {}
        decision_required = False
        hard_block = False
        profiles = [adapter.capability_profile() for adapter in self._adapters.values()]

        for item in work_items:
            if not isinstance(item, dict):
                raise OrchestratorError("each work item must be an object")
            candidate = item.get("candidate")
            if not isinstance(candidate, dict):
                raise OrchestratorError("each work item requires a candidate")
            work_package_id = _required_string(candidate, "workPackageId")
            if work_package_id in traces:
                raise OrchestratorError(f"duplicate work package: {work_package_id}")
            authorization = evaluate_authorization(
                policies, item.get("authorizationFacts", {})
            )
            record(
                "authorization.evaluated",
                "work-package",
                work_package_id,
                {
                    "decision": authorization.decision.value,
                    "controllingRules": list(authorization.controlling_rules),
                },
            )
            if authorization.decision not in {
                AuthorizationDecision.AUTO_PROCEED,
                AuthorizationDecision.AUTO_PROCEED_AND_RECORD,
                AuthorizationDecision.AUTO_PROCEED_WITHIN_BUDGET,
            }:
                decision_required |= (
                    authorization.decision
                    is AuthorizationDecision.USER_DECISION_REQUIRED
                )
                hard_block |= authorization.decision is AuthorizationDecision.BLOCKED
                traces[work_package_id] = WorkTrace(
                    work_package_id,
                    authorization.decision.value,
                    authorization.explanation,
                    None,
                    None,
                    "not_eligible",
                    None,
                    None,
                    (authorization.explanation,),
                )
                continue

            run = item.get("contextRun")
            if not isinstance(run, dict):
                raise OrchestratorError("authorized work requires contextRun")
            run = dict(run)
            run["modes"] = list(mode_ids)
            run["stage"] = stage
            try:
                manifest = compile_context(
                    recipe,
                    run,
                    item.get("contextItems", ()),
                    item.get("disclosureGrants", ()),
                    now,
                )
            except ContextError as error:
                hard_block = True
                traces[work_package_id] = WorkTrace(
                    work_package_id,
                    authorization.decision.value,
                    authorization.explanation,
                    None,
                    None,
                    "not_eligible",
                    None,
                    None,
                    (f"context compilation failed: {error}",),
                )
                record(
                    "context.rejected",
                    "work-package",
                    work_package_id,
                    {"reason": str(error)},
                )
                continue

            request = dict(item.get("runRequest", {}))
            request.update(
                {
                    "contextManifestId": manifest.manifest_id,
                    "contextManifestDigest": manifest.sha256,
                    "contextBytes": max(1, manifest.total_bytes),
                    "authorizationDecision": authorization.decision.value,
                }
            )
            try:
                profile, negotiations = select_adapter(request, profiles)
            except AdapterError as error:
                hard_block = True
                traces[work_package_id] = WorkTrace(
                    work_package_id,
                    authorization.decision.value,
                    authorization.explanation,
                    manifest.manifest_id,
                    None,
                    "not_eligible",
                    None,
                    None,
                    (f"capability negotiation failed: {error}",),
                )
                record(
                    "capability.rejected",
                    "agent-run",
                    request.get("runId", work_package_id),
                    {"reason": str(error)},
                )
                continue

            candidate = dict(candidate)
            candidate["adapterId"] = profile["adapterId"]
            prepared[work_package_id] = {
                "source": item,
                "candidate": candidate,
                "manifest": manifest,
                "request": request,
                "profile": profile,
            }
            selected_negotiation = next(
                result
                for result in negotiations
                if result.adapter_id == profile["adapterId"]
            )
            traces[work_package_id] = WorkTrace(
                work_package_id,
                authorization.decision.value,
                authorization.explanation,
                manifest.manifest_id,
                profile["adapterId"],
                "pending",
                None,
                None,
                tuple(
                    reason
                    for result in negotiations
                    if result.adapter_id != profile["adapterId"]
                    for reason in result.reasons
                ),
            )
            record(
                "capability.negotiated",
                "agent-run",
                request["runId"],
                {
                    "adapterId": profile["adapterId"],
                    "profileDigest": selected_negotiation.profile_digest,
                },
            )

        plan_dict: dict[str, Any] | None = None
        completions: list[dict[str, Any]] = []
        any_failure = False
        any_waiting = False

        if prepared:
            plan = schedule(
                [item["candidate"] for item in prepared.values()],
                scenario.get("activeReservations", ()),
                scenario.get("schedulerPolicy", {}),
                completed_dependencies=scenario.get("completedDependencies", ()),
                current_revisions=scenario.get("currentRevisions", {}),
                state_revision=state_revision,
                now=now,
            )
            plan_dict = schedule_plan_to_dict(plan)
            record(
                "schedule.planned",
                "project",
                project_id,
                {"selected": list(plan.selected_work_packages)},
            )
            decisions = {entry.work_package_id: entry for entry in plan.entries}
            for work_package_id, prepared_item in prepared.items():
                entry = decisions[work_package_id]
                current = traces[work_package_id]
                if entry.decision is ScheduleDecision.DEFERRED:
                    any_waiting = True
                    traces[work_package_id] = WorkTrace(
                        current.work_package_id,
                        current.authorization,
                        current.authorization_explanation,
                        current.context_manifest_id,
                        current.adapter_id,
                        entry.decision.value,
                        None,
                        None,
                        entry.reasons,
                    )
                    continue

                request = prepared_item["request"]
                profile = prepared_item["profile"]
                dispatch = build_dispatch(
                    request, profile, lease_id=f"LEASE-{request['runId']}"
                )
                record(
                    "run.dispatched",
                    "agent-run",
                    request["runId"],
                    {
                        "runId": request["runId"],
                        "workPackageId": work_package_id,
                        "dispatchDigest": dispatch["dispatchDigest"],
                        "externalSideEffectPossible": request["externalSideEffectPossible"],
                    },
                )
                raw = self._adapters[profile["adapterId"]].invoke(dispatch)
                normalized = normalize_provider_result(
                    raw,
                    dispatch,
                    provider_result_ref=f"provider-result:{request['runId']}",
                )
                record(
                    "run.completed",
                    "agent-run",
                    request["runId"],
                    {"runId": request["runId"], "status": normalized["status"]},
                )

                gate_outcome: str | None = None
                reasons = list(current.reasons)
                acceptance = prepared_item["source"].get("acceptance")
                if normalized["status"] == "completed" and isinstance(acceptance, dict):
                    gate = evaluate_gate(
                        acceptance["gate"],
                        acceptance["checkLibrary"],
                        acceptance["checkResults"],
                        acceptance["evidenceRecords"],
                        acceptance.get("facts", {}),
                        acceptance["subjectId"],
                        acceptance["subjectRevision"],
                        acceptance["evaluatedAt"],
                        acceptance.get("exceptions", ()),
                    )
                    gate_outcome = gate.outcome.value
                    reasons.extend(gate.reasons)
                    record(
                        "gate.evaluated",
                        "work-package",
                        work_package_id,
                        {"outcome": gate_outcome, "promotable": gate.promotable},
                    )
                    if not gate.promotable:
                        any_failure = True
                elif normalized["status"] == "completed":
                    any_failure = True
                    reasons.append("completed run has no acceptance Gate")
                elif normalized["status"] != "completed":
                    any_failure = True
                    reasons.append(f"run ended as {normalized['status']}")

                completion = prepared_item["source"].get("integrationCompletion")
                if (
                    normalized["status"] == "completed"
                    and gate_outcome in {GateOutcome.PASSED.value, GateOutcome.PASSED_WITH_EXCEPTION.value}
                    and isinstance(completion, dict)
                ):
                    completion = dict(completion)
                    completion.update(
                        {
                            "projectId": project_id,
                            "workPackageId": work_package_id,
                            "status": "completed",
                            "evidenceIds": normalized["evidenceIds"],
                        }
                    )
                    completions.append(completion)

                traces[work_package_id] = WorkTrace(
                    current.work_package_id,
                    current.authorization,
                    current.authorization_explanation,
                    current.context_manifest_id,
                    current.adapter_id,
                    entry.decision.value,
                    normalized["status"],
                    gate_outcome,
                    tuple(reasons),
                )

        integration_batch = None
        integration_status = None
        integration = scenario.get("integration")
        if integration is not None:
            if not isinstance(integration, dict):
                raise OrchestratorError("integration must be an object")
            expected_members = set(integration.get("memberWorkPackageIds", []))
            actual_members = {item["workPackageId"] for item in completions}
            if expected_members != actual_members:
                any_failure = True
                integration_status = "blocked"
                record(
                    "integration.blocked",
                    "integration-batch",
                    integration.get("batchId", "unknown"),
                    {"expectedMembers": sorted(expected_members), "readyMembers": sorted(actual_members)},
                )
            else:
                integration_batch = build_integration_batch(
                    completions,
                    batch_id=integration["batchId"],
                    target_revision=integration["targetRevision"],
                    owner_role=integration["ownerRole"],
                    required_checks=integration["requiredChecks"],
                )
                result = dict(integration["result"])
                result.update(
                    {
                        "schemaVersion": "0.1",
                        "batchId": integration_batch["batchId"],
                        "batchDigest": integration_batch["batchDigest"],
                        "targetRevision": integration_batch["targetRevision"],
                    }
                )
                validate_integration_result(result, integration_batch)
                integration_status = result["status"]
                any_failure |= integration_status != "passed"
                record(
                    "integration.evaluated",
                    "integration-batch",
                    integration_batch["batchId"],
                    {"status": integration_status},
                )

        if hard_block:
            status = "blocked"
            summary = "At least one required control blocked the work."
        elif decision_required:
            status = "decision_required"
            summary = "The next material action requires a user decision."
        elif any_failure:
            status = "failed"
            summary = "Execution or verification produced a result that cannot be accepted."
        elif any_waiting:
            status = "waiting"
            summary = "Safe work ran, while at least one package remains queued."
        else:
            status = "completed"
            summary = "All selected work and required combined checks passed."
        record(
            "orchestration.completed",
            "project",
            project_id,
            {"status": status},
        )
        trace = OrchestrationTrace(
            scenario_id,
            project_id,
            status,
            activation.decision.value,
            selection.route_id,
            stage,
            mode_ids,
            state_revision,
            tuple(traces[item["candidate"]["workPackageId"]] for item in work_items),
            plan_dict,
            integration_batch,
            integration_status,
            histories,
            summary,
        )
        validate_trace(trace)
        return trace

    @staticmethod
    def recover(
        events: Iterable[dict[str, Any]],
        leases: Iterable[dict[str, Any]],
        external_observations: dict[str, str],
        *,
        now: str,
        max_attempts: int,
    ):
        return plan_recovery(
            events, leases, external_observations, now, max_attempts
        )
