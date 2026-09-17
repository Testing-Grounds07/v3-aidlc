import copy
import json
import unittest
from pathlib import Path

from v3_aidlc.scheduler import (
    ScheduleDecision,
    SchedulerError,
    build_integration_batch,
    claims_conflict,
    schedule,
    schedule_plan_to_dict,
    validate_integration_batch,
    validate_integration_result,
)


NOW = "2026-09-17T12:00:00Z"


def policy(**overrides):
    value = {
        "schemaVersion": "0.1",
        "policyId": "SCHED-1",
        "version": "0.1",
        "limits": {
            "project-runs": 3,
            "adapter:alpha": 2,
            "workstream:core": 2,
        },
        "agingWindowSeconds": 3600,
        "maxAgingBoost": 3,
    }
    value.update(overrides)
    return value


def candidate(work_package_id, domain, access="write", **overrides):
    value = {
        "schemaVersion": "0.1",
        "projectId": "PRJ-1",
        "workPackageId": work_package_id,
        "subjectRevision": f"rev-{work_package_id}",
        "workstreamId": "core",
        "adapterId": "alpha",
        "role": "implementer",
        "priorityClass": "normal",
        "userPriority": 0,
        "queuedAt": "2026-09-17T11:00:00Z",
        "dependencyIds": [],
        "claims": [{"domain": domain, "access": access}],
        "quotaCosts": {
            "project-runs": 1,
            "adapter:alpha": 1,
            "workstream:core": 1,
        },
    }
    value.update(overrides)
    return value


def revisions(*ids):
    return {item: f"rev-{item}" for item in ids}


def reservation(work_package_id, domain, access="write", **overrides):
    value = {
        "reservationId": f"RES-{work_package_id}",
        "projectId": "PRJ-1",
        "workPackageId": work_package_id,
        "subjectRevision": f"rev-{work_package_id}",
        "claims": [{"domain": domain, "access": access}],
        "quotaCosts": {"project-runs": 1, "adapter:alpha": 1, "workstream:core": 1},
    }
    value.update(overrides)
    return value


def completion(work_package_id, **overrides):
    value = {
        "projectId": "PRJ-1",
        "workPackageId": work_package_id,
        "subjectRevision": f"rev-{work_package_id}-done",
        "baseRevision": "main-1",
        "integrationGroup": "release-a",
        "artifactDigest": ("a" if work_package_id == "WP-1" else "b") * 64,
        "status": "completed",
        "evidenceIds": [f"EVID-{work_package_id}"],
    }
    value.update(overrides)
    return value


def make_schedule(candidates, active=(), **kwargs):
    ids = [item["workPackageId"] for item in candidates]
    return schedule(
        candidates,
        active,
        policy(),
        completed_dependencies=kwargs.get("completed", ()),
        current_revisions=kwargs.get("current_revisions", revisions(*ids)),
        state_revision="STATE-1",
        now=NOW,
    )


class SchedulerTest(unittest.TestCase):
    def test_reads_can_share_a_conflict_domain(self):
        self.assertFalse(
            claims_conflict(
                {"domain": "repo:catalog", "access": "read"},
                {"domain": "repo:catalog", "access": "read"},
            )
        )
        plan = make_schedule(
            [
                candidate("WP-1", "repo:catalog", "read"),
                candidate("WP-2", "repo:catalog", "read"),
            ]
        )
        self.assertEqual(plan.selected_work_packages, ("WP-1", "WP-2"))

    def test_write_conflicts_with_read_and_write(self):
        for access in ("read", "write", "exclusive"):
            with self.subTest(access=access):
                self.assertTrue(
                    claims_conflict(
                        {"domain": "repo:catalog", "access": "write"},
                        {"domain": "repo:catalog", "access": access},
                    )
                )

    def test_separate_domains_run_in_parallel(self):
        plan = make_schedule(
            [candidate("WP-1", "repo:file:a"), candidate("WP-2", "repo:file:b")]
        )
        self.assertEqual(plan.selected_work_packages, ("WP-1", "WP-2"))
        serialized = schedule_plan_to_dict(plan)
        self.assertEqual(serialized["selectedWorkPackageIds"], ["WP-1", "WP-2"])
        self.assertEqual(serialized["stateRevision"], "STATE-1")

    def test_active_reservation_blocks_conflicting_candidate(self):
        plan = make_schedule(
            [candidate("WP-1", "database:schema")],
            [reservation("WP-ACTIVE", "database:schema")],
        )
        self.assertEqual(plan.entries[0].decision, ScheduleDecision.DEFERRED)
        self.assertIn("WP-ACTIVE", plan.entries[0].reasons[0])

    def test_selected_candidate_reserves_against_later_candidate(self):
        plan = make_schedule(
            [candidate("WP-1", "repo:file:a"), candidate("WP-2", "repo:file:a")]
        )
        self.assertEqual(plan.selected_work_packages, ("WP-1",))
        self.assertEqual(plan.entries[1].decision, ScheduleDecision.DEFERRED)

    def test_incomplete_dependency_defers_work(self):
        plan = make_schedule(
            [candidate("WP-1", "repo:file:a", dependencyIds=["WP-0"])]
        )
        self.assertIn("dependency incomplete: WP-0", plan.entries[0].reasons)

    def test_completed_dependency_allows_work(self):
        plan = make_schedule(
            [candidate("WP-1", "repo:file:a", dependencyIds=["WP-0"])],
            completed=["WP-0"],
        )
        self.assertEqual(plan.selected_work_packages, ("WP-1",))

    def test_stale_revision_defers_work(self):
        plan = make_schedule(
            [candidate("WP-1", "repo:file:a")],
            current_revisions={"WP-1": "rev-new"},
        )
        self.assertIn("subject revision is stale", plan.entries[0].reasons)

    def test_unknown_revision_fails_closed(self):
        plan = make_schedule(
            [candidate("WP-1", "repo:file:a")], current_revisions={}
        )
        self.assertIn("current subject revision is unknown", plan.entries[0].reasons)

    def test_active_usage_counts_against_quota(self):
        plan = make_schedule(
            [candidate("WP-1", "repo:file:a")],
            [
                reservation("ACTIVE-1", "repo:file:x"),
                reservation("ACTIVE-2", "repo:file:y"),
            ],
        )
        self.assertIn("quota exceeded: adapter:alpha", plan.entries[0].reasons)

    def test_unknown_quota_dimension_defers_work(self):
        item = candidate("WP-1", "repo:file:a")
        item["quotaCosts"]["gpu"] = 1
        plan = make_schedule([item])
        self.assertIn("unknown quota dimension: gpu", plan.entries[0].reasons)

    def test_safety_work_orders_before_normal_work(self):
        plan = make_schedule(
            [
                candidate("WP-NORMAL", "repo:file:a"),
                candidate("WP-SAFE", "repo:file:b", priorityClass="safety_recovery"),
            ]
        )
        self.assertEqual(plan.selected_work_packages[0], "WP-SAFE")

    def test_aging_prevents_normal_work_from_waiting_forever(self):
        old = candidate(
            "WP-OLD", "repo:file:a", queuedAt="2026-09-17T05:00:00Z"
        )
        new = candidate(
            "WP-NEW",
            "repo:file:a",
            priorityClass="integration_blocker",
            queuedAt="2026-09-17T11:59:00Z",
        )
        plan = make_schedule([new, old])
        self.assertEqual(plan.selected_work_packages, ("WP-OLD",))

    def test_user_priority_breaks_equal_priority_ties(self):
        plan = make_schedule(
            [
                candidate("WP-LOW", "repo:file:a", userPriority=1),
                candidate("WP-HIGH", "repo:file:a", userPriority=10),
            ]
        )
        self.assertEqual(plan.selected_work_packages, ("WP-HIGH",))

    def test_duplicate_work_package_is_rejected(self):
        with self.assertRaisesRegex(SchedulerError, "unique"):
            make_schedule(
                [candidate("WP-1", "repo:file:a"), candidate("WP-1", "repo:file:b")]
            )

    def test_schedule_cannot_span_projects(self):
        with self.assertRaisesRegex(SchedulerError, "multiple projects"):
            make_schedule(
                [
                    candidate("WP-1", "repo:file:a"),
                    candidate("WP-2", "repo:file:b", projectId="PRJ-2"),
                ]
            )

    def test_integration_batch_is_stable_and_revision_bound(self):
        batch = build_integration_batch(
            [completion("WP-2"), completion("WP-1")],
            batch_id="INT-1",
            target_revision="main-1",
            owner_role="integrator",
            required_checks=["tests", "review"],
        )
        self.assertEqual(
            [item["workPackageId"] for item in batch["members"]], ["WP-1", "WP-2"]
        )
        self.assertEqual(len(batch["batchDigest"]), 64)
        validate_integration_batch(batch)

    def test_tampered_integration_batch_is_rejected(self):
        batch = build_integration_batch(
            [completion("WP-1")],
            batch_id="INT-1",
            target_revision="main-1",
            owner_role="integrator",
            required_checks=["tests"],
        )
        batch["members"][0]["subjectRevision"] = "tampered"
        with self.assertRaisesRegex(SchedulerError, "digest"):
            validate_integration_batch(batch)

    def test_stale_integration_member_is_rejected(self):
        with self.assertRaisesRegex(SchedulerError, "stale base"):
            build_integration_batch(
                [completion("WP-1", baseRevision="main-0")],
                batch_id="INT-1",
                target_revision="main-1",
                owner_role="integrator",
                required_checks=["tests"],
            )

    def test_integration_cannot_span_groups(self):
        with self.assertRaisesRegex(SchedulerError, "integration groups"):
            build_integration_batch(
                [completion("WP-1"), completion("WP-2", integrationGroup="release-b")],
                batch_id="INT-1",
                target_revision="main-1",
                owner_role="integrator",
                required_checks=["tests"],
            )

    def test_passed_integration_requires_all_checks_evidence_and_revision(self):
        batch = build_integration_batch(
            [completion("WP-1"), completion("WP-2")],
            batch_id="INT-1",
            target_revision="main-1",
            owner_role="integrator",
            required_checks=["tests", "review"],
        )
        result = {
            "schemaVersion": "0.1",
            "batchId": "INT-1",
            "batchDigest": batch["batchDigest"],
            "targetRevision": "main-1",
            "resultingRevision": "main-2",
            "status": "passed",
            "summary": "Integrated and verified.",
            "checkResults": {"tests": "passed", "review": "passed"},
            "evidenceIds": ["EVID-INT-1"],
        }
        validate_integration_result(result, batch)
        for mutation, message in (
            ({"checkResults": {"tests": "passed", "review": "failed"}}, "every check"),
            ({"evidenceIds": []}, "requires evidence"),
            ({"resultingRevision": "main-1"}, "must differ"),
        ):
            with self.subTest(message=message):
                changed = copy.deepcopy(result)
                changed.update(mutation)
                with self.assertRaisesRegex(SchedulerError, message):
                    validate_integration_result(changed, batch)

    def test_failed_integration_cannot_claim_new_revision(self):
        batch = build_integration_batch(
            [completion("WP-1")],
            batch_id="INT-1",
            target_revision="main-1",
            owner_role="integrator",
            required_checks=["tests"],
        )
        result = {
            "schemaVersion": "0.1",
            "batchId": "INT-1",
            "batchDigest": batch["batchDigest"],
            "targetRevision": "main-1",
            "resultingRevision": "main-2",
            "status": "failed",
            "summary": "Integration tests failed.",
            "checkResults": {"tests": "failed"},
            "evidenceIds": ["EVID-FAIL"],
        }
        with self.assertRaisesRegex(SchedulerError, "cannot claim"):
            validate_integration_result(result, batch)

    def test_scheduler_schemas_are_valid_json(self):
        schema_dir = Path(__file__).parents[1] / "schemas"
        for name in (
            "scheduler-policy.schema.json",
            "schedule-candidate.schema.json",
            "schedule-plan.schema.json",
            "conflict-reservation.schema.json",
            "integration-batch.schema.json",
            "integration-result.schema.json",
        ):
            with self.subTest(name=name):
                json.loads((schema_dir / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
