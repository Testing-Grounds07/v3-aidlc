import copy
import unittest

from v3_aidlc.recovery import (
    RecoveryAction,
    RecoveryError,
    append_event,
    plan_recovery,
    require_finding_transition,
    validate_finding,
    validate_learning,
    verify_event_chain,
)


def draft(event_id, event_type, payload, key, causation_id=None):
    value = {
        "schemaVersion": "0.1",
        "eventId": event_id,
        "projectId": "PRJ-1",
        "streamId": "project:PRJ-1",
        "eventType": event_type,
        "aggregateType": "agent-run",
        "aggregateId": payload.get("runId", "PRJ-1"),
        "occurredAt": "2026-09-16T10:00:00Z",
        "recordedAt": "2026-09-16T10:00:01Z",
        "actor": {"type": "project_lead", "id": "lead-1"},
        "idempotencyKey": key,
        "payload": payload,
    }
    if causation_id:
        value["causationId"] = causation_id
    return value


def history_for_run(run_id="RUN-1", external=False, effect_key=None, completed=False):
    payload = {
        "runId": run_id,
        "externalSideEffectPossible": external,
    }
    if effect_key:
        payload["effectKey"] = effect_key
    events, dispatched, _ = append_event(
        (), draft("EVT-1", "run.dispatched", payload, f"dispatch:{run_id}")
    )
    if completed:
        events, _, _ = append_event(
            events,
            draft(
                "EVT-2",
                "run.completed",
                {"runId": run_id},
                f"complete:{run_id}",
                dispatched["eventId"],
            ),
        )
    return events


def lease(run_id="RUN-1", expires="2026-09-16T11:00:00Z", attempt=1, status="active"):
    return {
        "schemaVersion": "0.1",
        "leaseId": f"LEASE-{run_id}",
        "projectId": "PRJ-1",
        "resourceType": "work-package",
        "resourceId": "WP-1",
        "holderRunId": run_id,
        "acquiredAt": "2026-09-16T10:00:00Z",
        "heartbeatAt": "2026-09-16T10:30:00Z",
        "expiresAt": expires,
        "status": status,
        "attempt": attempt,
        "contextManifestId": "CTX-1",
        "dispatchDigest": "a" * 64,
        "idempotencyKey": f"lease:{run_id}",
    }


class RecoveryTest(unittest.TestCase):
    def test_append_builds_verifiable_hash_chain(self):
        events, first, appended = append_event(
            (), draft("EVT-1", "project.started", {}, "start")
        )
        events, second, _ = append_event(
            events,
            draft("EVT-2", "project.updated", {}, "update", first["eventId"]),
        )
        self.assertTrue(appended)
        self.assertEqual(second["previousEventHash"], first["eventHash"])
        verify_event_chain(events)

    def test_tampered_event_is_detected(self):
        events = history_for_run()
        tampered = [copy.deepcopy(events[0])]
        tampered[0]["payload"]["runId"] = "RUN-CHANGED"
        with self.assertRaisesRegex(RecoveryError, "content hash"):
            verify_event_chain(tampered)

    def test_identical_idempotent_append_returns_existing_event(self):
        event_draft = draft("EVT-1", "project.started", {}, "start")
        events, existing, _ = append_event((), event_draft)
        same_events, same, appended = append_event(events, event_draft)
        self.assertFalse(appended)
        self.assertEqual(existing, same)
        self.assertEqual(events, same_events)

    def test_idempotency_key_cannot_change_meaning(self):
        events, _, _ = append_event(
            (), draft("EVT-1", "project.started", {}, "same-key")
        )
        with self.assertRaisesRegex(RecoveryError, "different event data"):
            append_event(
                events, draft("EVT-2", "project.cancelled", {}, "same-key")
            )

    def test_causation_must_reference_earlier_event(self):
        with self.assertRaisesRegex(RecoveryError, "earlier event"):
            append_event(
                (),
                draft("EVT-1", "project.updated", {}, "update", "EVT-MISSING"),
            )

    def test_open_finding_cannot_claim_resolution(self):
        finding = {
            "schemaVersion": "0.1",
            "id": "FIND-1",
            "projectId": "PRJ-1",
            "subjectId": "WP-1",
            "subjectRevision": "rev-1",
            "sourceEventId": "EVT-1",
            "category": "defect",
            "severity": "high",
            "status": "open",
            "summary": "A defect exists",
            "details": "The expected behavior differs.",
            "evidenceIds": ["EVID-1"],
            "ownerRole": "implementer",
            "discoveredAt": "2026-09-16T10:00:00Z",
            "resolution": "Not actually resolved",
        }
        with self.assertRaisesRegex(RecoveryError, "cannot claim"):
            validate_finding(finding)

    def test_resolved_finding_requires_resolution_evidence(self):
        finding = {
            "schemaVersion": "0.1",
            "id": "FIND-1",
            "projectId": "PRJ-1",
            "subjectId": "WP-1",
            "subjectRevision": "rev-2",
            "sourceEventId": "EVT-1",
            "category": "defect",
            "severity": "high",
            "status": "resolved",
            "summary": "A defect existed",
            "details": "The expected behavior differed.",
            "evidenceIds": ["EVID-1"],
            "ownerRole": "implementer",
            "discoveredAt": "2026-09-16T10:00:00Z",
            "resolution": "Corrected and retested",
            "resolutionEventId": "EVT-2",
            "resolvedAt": "2026-09-16T11:00:00Z",
        }
        with self.assertRaisesRegex(RecoveryError, "resolutionEvidenceIds"):
            validate_finding(finding)

    def test_accepted_risk_can_reopen_for_repair(self):
        require_finding_transition("accepted_risk", "repairing")
        with self.assertRaisesRegex(RecoveryError, "cannot transition"):
            require_finding_transition("resolved", "repairing")

    def test_validated_learning_requires_evidence(self):
        learning = {
            "schemaVersion": "0.1",
            "id": "LEARN-1",
            "projectId": "PRJ-1",
            "learningType": "negative_result",
            "confidence": "validated",
            "status": "active",
            "statement": "This API cannot satisfy the latency target.",
            "sourceFindingIds": ["FIND-1"],
            "sourceEventIds": [],
            "evidenceIds": [],
            "applicabilityTags": ["api-a", "latency"],
            "createdAt": "2026-09-16T10:00:00Z",
            "createdBy": "lead-1",
        }
        with self.assertRaisesRegex(RecoveryError, "requires evidence"):
            validate_learning(learning)

    def test_unexpired_lease_waits(self):
        plan = plan_recovery(
            history_for_run(),
            [lease(expires="2026-09-16T13:00:00Z")],
            {},
            "2026-09-16T12:00:00Z",
            3,
        )
        self.assertEqual(plan.steps[0].action, RecoveryAction.WAIT_FOR_LEASE)

    def test_expired_local_run_is_reclaimed_with_budget(self):
        plan = plan_recovery(
            history_for_run(), [lease()], {}, "2026-09-16T12:00:00Z", 3
        )
        self.assertEqual(plan.steps[0].action, RecoveryAction.RECLAIM_AND_REQUEUE)

    def test_external_effect_is_verified_before_retry(self):
        plan = plan_recovery(
            history_for_run(external=True, effect_key="deploy:1"),
            [lease()],
            {},
            "2026-09-16T12:00:00Z",
            3,
        )
        self.assertEqual(plan.steps[0].action, RecoveryAction.VERIFY_EXTERNAL_EFFECT)

    def test_confirmed_external_effect_is_not_repeated(self):
        plan = plan_recovery(
            history_for_run(external=True, effect_key="deploy:1"),
            [lease()],
            {"deploy:1": "succeeded"},
            "2026-09-16T12:00:00Z",
            3,
        )
        self.assertEqual(
            plan.steps[0].action, RecoveryAction.RECONCILE_COMPLETED_RUN
        )

    def test_exhausted_attempt_budget_escalates(self):
        plan = plan_recovery(
            history_for_run(), [lease(attempt=3)], {}, "2026-09-16T12:00:00Z", 3
        )
        self.assertEqual(
            plan.steps[0].action, RecoveryAction.ESCALATE_ATTEMPT_BUDGET
        )

    def test_completed_run_with_active_lease_reconciles(self):
        plan = plan_recovery(
            history_for_run(completed=True),
            [lease(expires="2026-09-16T13:00:00Z")],
            {},
            "2026-09-16T12:00:00Z",
            3,
        )
        self.assertEqual(
            plan.steps[0].action, RecoveryAction.RECONCILE_COMPLETED_RUN
        )

    def test_dispatch_without_lease_is_orphaned_not_retried(self):
        plan = plan_recovery(
            history_for_run(), [], {}, "2026-09-16T12:00:00Z", 3
        )
        self.assertEqual(plan.steps[0].action, RecoveryAction.RECONCILE_ORPHAN_RUN)


if __name__ == "__main__":
    unittest.main()
