import json
import unittest
from pathlib import Path

from v3_aidlc.recovery import RecoveryAction, append_event, verify_event_chain
from v3_aidlc.reference_orchestrator import (
    OrchestratorError,
    ReferenceOrchestrator,
    trace_to_dict,
    validate_trace,
)


ROOT = Path(__file__).parents[1]
NOW = "2026-09-17T12:00:00Z"


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class FakeAdapter:
    def __init__(self, adapter_id="fake-capable", capabilities=None, status="completed"):
        self.adapter_id = adapter_id
        self.capabilities = capabilities or ["code_edit", "test_execution"]
        self.status = status

    def capability_profile(self):
        return {
            "schemaVersion": "0.1",
            "profileId": f"PROFILE-{self.adapter_id}",
            "adapterId": self.adapter_id,
            "adapterVersion": "1.0.0",
            "provider": "conformance",
            "model": "deterministic-fake",
            "status": "available",
            "roles": ["implementer"],
            "capabilities": self.capabilities,
            "modalities": ["text"],
            "tools": ["filesystem.write", "tests.run"],
            "networkHosts": [],
            "maxContextBytes": 100_000,
            "maxOutputBytes": 20_000,
            "maxConcurrentRuns": 4,
            "maxSensitivity": "confidential",
            "structuredOutput": True,
            "streaming": False,
            "externalSideEffects": False,
            "idempotentInvocation": True,
        }

    def invoke(self, dispatch):
        work_package_id = dispatch["workPackageId"]
        return {
            "startedAt": NOW,
            "finishedAt": NOW,
            "status": self.status,
            "summary": f"Deterministic result for {work_package_id}.",
            "artifactIds": [f"ART-{work_package_id}"],
            "evidenceIds": [f"EVID-{work_package_id}"],
            "satisfiedCriteria": (
                dispatch["request"]["completionCriteria"]
                if self.status == "completed"
                else []
            ),
            "findingIds": [],
            "externalEffects": [],
            "usage": {"inputUnits": 100, "outputUnits": 20},
        }


def context_items(work_package_id):
    definitions = (
        ("objective", "user_instruction", "Build the bounded feature."),
        ("requirement", "canonical_state", "The feature must pass its tests."),
        ("constraint", "project_policy", "Do not change unrelated behavior."),
        ("tool_contract", "governed_contract", "Use only allowed local tools."),
    )
    result = []
    for number, (kind, source, content) in enumerate(definitions, start=1):
        result.append(
            {
                "id": f"CTXITEM-{work_package_id}-{number}",
                "revision": "1",
                "kind": kind,
                "sourceType": source,
                "sourceRef": f"source:{number}",
                "sensitivity": "internal",
                "integrity": "authoritative",
                "projectId": "PRJ-1",
                "createdAt": "2026-09-17T10:00:00Z",
                "claimKey": f"{work_package_id}:{kind}",
                "entityIds": [work_package_id],
                "stages": ["design"],
                "modes": [],
                "roles": ["implementer"],
                "relevanceTags": ["bounded-change"],
                "alwaysInclude": False,
                "content": content,
            }
        )
    return result


def acceptance(work_package_id, passed=True):
    revision = f"rev-{work_package_id}"
    evidence_id = f"EVID-{work_package_id}"
    check = load("checks/automated-tests.json")
    gate = {
        "schemaVersion": "0.1",
        "id": "GATE-CONFORMANCE",
        "version": "1.0.0",
        "title": "Conformance acceptance",
        "gateType": "package",
        "acceptedExceptionAuthorities": [],
        "checkRules": [
            {
                "checkId": check["id"],
                "requirement": "required",
                "waivable": False,
                "hardControl": True,
            }
        ],
    }
    evidence = {
        "id": evidence_id,
        "kind": "test_result",
        "subjectId": work_package_id,
        "subjectRevision": revision,
        "producerId": "fake-capable",
        "producerRole": "implementer",
        "producerIndependenceGroup": "implementation",
        "collectedAt": NOW,
        "locator": f"evidence:{evidence_id}",
        "sha256": "a" * 64,
        "assertions": ["The bounded automated suite passed."],
    }
    result = {
        "checkId": check["id"],
        "checkVersion": check["version"],
        "status": "passed" if passed else "failed",
        "subjectId": work_package_id,
        "subjectRevision": revision,
        "evaluatedAt": NOW,
        "evaluator": {
            "id": "test-runner",
            "role": "test_runner",
            "independenceGroup": "verification",
        },
        "subjectProducerIndependenceGroup": "implementation",
        "evidenceIds": [evidence_id],
    }
    return {
        "gate": gate,
        "checkLibrary": {check["id"]: check},
        "checkResults": [result],
        "evidenceRecords": [evidence],
        "facts": {},
        "subjectId": work_package_id,
        "subjectRevision": revision,
        "evaluatedAt": NOW,
    }


def work(work_package_id, domain=None, *, authorization=None, passed=True):
    domain = domain or f"repo:file:{work_package_id.lower()}"
    return {
        "candidate": {
            "schemaVersion": "0.1",
            "projectId": "PRJ-1",
            "workPackageId": work_package_id,
            "subjectRevision": f"rev-{work_package_id}",
            "workstreamId": "core",
            "adapterId": "unselected",
            "role": "implementer",
            "priorityClass": "normal",
            "userPriority": 0,
            "queuedAt": "2026-09-17T11:00:00Z",
            "dependencyIds": [],
            "claims": [{"domain": domain, "access": "write"}],
            "quotaCosts": {"project-runs": 1, "adapter:fake-capable": 1},
        },
        "authorizationFacts": authorization
        or {
            "actionType": "implement",
            "impact": "local_reversible",
            "scopeChange": "none",
            "hasRequiredPermission": True,
        },
        "contextRun": {
            "runId": f"RUN-{work_package_id}",
            "projectId": "PRJ-1",
            "role": "implementer",
            "entityIds": [work_package_id],
            "modes": [],
            "taskTags": ["bounded-change"],
        },
        "contextItems": context_items(work_package_id),
        "disclosureGrants": [],
        "runRequest": {
            "schemaVersion": "0.1",
            "runId": f"RUN-{work_package_id}",
            "projectId": "PRJ-1",
            "workPackageId": work_package_id,
            "role": "implementer",
            "objective": "Implement the bounded change.",
            "contextManifestId": "pending",
            "contextManifestDigest": "0" * 64,
            "contextBytes": 1,
            "sensitivity": "internal",
            "requiredCapabilities": ["code_edit", "test_execution"],
            "requiredModalities": ["text"],
            "requiredTools": ["filesystem.write", "tests.run"],
            "requiredNetworkHosts": [],
            "structuredOutputRequired": True,
            "externalSideEffectPossible": False,
            "maxOutputBytes": 10_000,
            "completionCriteria": ["implemented", "tests-passed"],
            "authorizationDecision": "pending",
            "attempt": 1,
            "idempotencyKey": f"run:{work_package_id}:1",
        },
        "acceptance": acceptance(work_package_id, passed),
        "integrationCompletion": {
            "subjectRevision": f"rev-{work_package_id}",
            "baseRevision": "main-1",
            "integrationGroup": "release-a",
            "artifactDigest": ("a" if work_package_id.endswith("1") else "b") * 64,
        },
    }


def scenario(work_items):
    mode_library = {}
    for path in (ROOT / "modes").glob("*.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        mode_library[item["id"]] = item
    return {
        "scenarioId": "SCENARIO-1",
        "projectId": "PRJ-1",
        "stateRevision": "STATE-1",
        "now": NOW,
        "activationFacts": {"existingProjectRef": "PRJ-1"},
        "route": load("routes/production-ready.json"),
        "modeLibrary": mode_library,
        "stage": "design",
        "routeFacts": {"userFacing": False},
        "posture": "balanced",
        "authorizationPolicies": [load("policies/governed-development.json")],
        "contextRecipe": load("context-recipes/implementation.json"),
        "work": work_items,
        "activeReservations": [],
        "schedulerPolicy": {
            "schemaVersion": "0.1",
            "policyId": "SCHED-CONFORMANCE",
            "version": "0.1",
            "limits": {"project-runs": 4, "adapter:fake-capable": 4},
            "agingWindowSeconds": 3600,
            "maxAgingBoost": 3,
        },
        "completedDependencies": [],
        "currentRevisions": {
            item["candidate"]["workPackageId"]: item["candidate"]["subjectRevision"]
            for item in work_items
        },
    }


def recovery_event_history(external=False):
    payload = {"runId": "RUN-1", "externalSideEffectPossible": external}
    if external:
        payload["effectKey"] = "deploy:1"
    draft = {
        "schemaVersion": "0.1",
        "eventId": "EVT-1",
        "projectId": "PRJ-1",
        "streamId": "project:PRJ-1",
        "eventType": "run.dispatched",
        "aggregateType": "agent-run",
        "aggregateId": "RUN-1",
        "occurredAt": "2026-09-17T10:00:00Z",
        "recordedAt": "2026-09-17T10:00:00Z",
        "actor": {"type": "project_lead", "id": "lead-1"},
        "idempotencyKey": "dispatch:1",
        "payload": payload,
    }
    events, _, _ = append_event((), draft)
    return events


class ReferenceOrchestratorTest(unittest.TestCase):
    def test_simple_conversation_does_not_activate_managed_runtime(self):
        runtime = ReferenceOrchestrator([FakeAdapter()])
        value = scenario([work("WP-1")])
        value["activationFacts"] = {}
        trace = runtime.execute(value)
        self.assertEqual(trace.status, "not_managed")
        self.assertEqual(trace.events, ())

    def test_complete_single_work_journey(self):
        trace = ReferenceOrchestrator([FakeAdapter()]).execute(scenario([work("WP-1")]))
        self.assertEqual(trace.status, "completed")
        self.assertEqual(trace.work[0].authorization, "auto_proceed")
        self.assertEqual(trace.work[0].schedule_decision, "selected")
        self.assertEqual(trace.work[0].run_status, "completed")
        self.assertEqual(trace.work[0].gate_outcome, "passed")
        verify_event_chain(trace.events)
        validate_trace(trace)

    def test_missing_permission_blocks_before_context_or_dispatch(self):
        item = work(
            "WP-1",
            authorization={
                "actionType": "implement",
                "impact": "local_reversible",
                "scopeChange": "none",
                "hasRequiredPermission": False,
            },
        )
        trace = ReferenceOrchestrator([FakeAdapter()]).execute(scenario([item]))
        self.assertEqual(trace.status, "blocked")
        self.assertIsNone(trace.work[0].context_manifest_id)
        self.assertIsNone(trace.work[0].run_status)

    def test_irreversible_external_action_requests_user_decision(self):
        item = work(
            "WP-1",
            authorization={
                "actionType": "operate",
                "impact": "external_irreversible",
                "scopeChange": "none",
                "hasRequiredPermission": True,
            },
        )
        trace = ReferenceOrchestrator([FakeAdapter()]).execute(scenario([item]))
        self.assertEqual(trace.status, "decision_required")
        self.assertEqual(trace.work[0].authorization, "user_decision_required")

    def test_capability_mismatch_blocks_before_scheduling(self):
        runtime = ReferenceOrchestrator([FakeAdapter(capabilities=["code_edit"])])
        trace = runtime.execute(scenario([work("WP-1")]))
        self.assertEqual(trace.status, "blocked")
        self.assertIn("capability negotiation failed", trace.work[0].reasons[0])

    def test_independent_work_runs_and_integrates_as_one_batch(self):
        value = scenario([work("WP-1"), work("WP-2")])
        value["integration"] = {
            "batchId": "INT-1",
            "targetRevision": "main-1",
            "ownerRole": "integrator",
            "requiredChecks": ["combined-tests"],
            "memberWorkPackageIds": ["WP-1", "WP-2"],
            "result": {
                "status": "passed",
                "summary": "Combined checks passed.",
                "checkResults": {"combined-tests": "passed"},
                "evidenceIds": ["EVID-INTEGRATION"],
                "resultingRevision": "main-2",
            },
        }
        trace = ReferenceOrchestrator([FakeAdapter()]).execute(value)
        self.assertEqual(trace.status, "completed")
        self.assertEqual(trace.integration_status, "passed")
        self.assertEqual(len(trace.integration_batch["members"]), 2)

    def test_conflicting_parallel_work_leaves_one_waiting(self):
        value = scenario(
            [work("WP-1", "database:schema"), work("WP-2", "database:schema")]
        )
        trace = ReferenceOrchestrator([FakeAdapter()]).execute(value)
        self.assertEqual(trace.status, "waiting")
        decisions = [item.schedule_decision for item in trace.work]
        self.assertEqual(decisions.count("selected"), 1)
        self.assertEqual(decisions.count("deferred"), 1)

    def test_failed_gate_prevents_acceptance(self):
        trace = ReferenceOrchestrator([FakeAdapter()]).execute(
            scenario([work("WP-1", passed=False)])
        )
        self.assertEqual(trace.status, "failed")
        self.assertEqual(trace.work[0].gate_outcome, "failed")

    def test_trace_serializes_to_stable_public_contract(self):
        trace = ReferenceOrchestrator([FakeAdapter()]).execute(scenario([work("WP-1")]))
        payload = trace_to_dict(trace)
        self.assertEqual(payload["schemaVersion"], "0.1")
        self.assertEqual(payload["work"][0]["workPackageId"], "WP-1")
        self.assertNotIn("rawProviderResult", json.dumps(payload))

    def test_trace_detects_schedule_tampering(self):
        trace = ReferenceOrchestrator([FakeAdapter()]).execute(scenario([work("WP-1")]))
        trace.schedule_plan["selectedWorkPackageIds"] = []
        with self.assertRaisesRegex(OrchestratorError, "schedule"):
            validate_trace(trace)

    def test_recovery_requeues_expired_reversible_work(self):
        lease = {
            "schemaVersion": "0.1",
            "leaseId": "LEASE-1",
            "projectId": "PRJ-1",
            "resourceType": "work-package",
            "resourceId": "WP-1",
            "holderRunId": "RUN-1",
            "acquiredAt": "2026-09-17T10:00:00Z",
            "heartbeatAt": "2026-09-17T10:15:00Z",
            "expiresAt": "2026-09-17T10:30:00Z",
            "status": "active",
            "attempt": 1,
            "contextManifestId": "CTX-1",
            "dispatchDigest": "a" * 64,
            "idempotencyKey": "lease:1",
        }
        plan = ReferenceOrchestrator.recover(
            recovery_event_history(), [lease], {}, now=NOW, max_attempts=3
        )
        self.assertEqual(plan.steps[0].action, RecoveryAction.RECLAIM_AND_REQUEUE)

    def test_recovery_verifies_possible_external_effect_before_retry(self):
        lease = {
            "schemaVersion": "0.1",
            "leaseId": "LEASE-1",
            "projectId": "PRJ-1",
            "resourceType": "work-package",
            "resourceId": "WP-1",
            "holderRunId": "RUN-1",
            "acquiredAt": "2026-09-17T10:00:00Z",
            "heartbeatAt": "2026-09-17T10:15:00Z",
            "expiresAt": "2026-09-17T10:30:00Z",
            "status": "active",
            "attempt": 1,
            "contextManifestId": "CTX-1",
            "dispatchDigest": "a" * 64,
            "idempotencyKey": "lease:1",
        }
        plan = ReferenceOrchestrator.recover(
            recovery_event_history(external=True),
            [lease],
            {},
            now=NOW,
            max_attempts=3,
        )
        self.assertEqual(plan.steps[0].action, RecoveryAction.VERIFY_EXTERNAL_EFFECT)

    def test_orchestrator_schemas_and_catalog_are_valid_json(self):
        for path in (
            ROOT / "schemas/orchestration-trace.schema.json",
            ROOT / "schemas/conformance-scenario.schema.json",
            ROOT / "conformance/scenarios.json",
        ):
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
