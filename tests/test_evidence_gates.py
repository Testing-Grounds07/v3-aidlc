import copy
import unittest
from pathlib import Path

from v3_aidlc.evidence_gates import (
    EvidenceGateError,
    GateOutcome,
    evaluate_gate,
    load_check_library,
    load_contract,
    validate_gate_contract,
)


ROOT = Path(__file__).parents[1]
DIGEST = "a" * 64


def evidence(identifier, kind, group="implementation", revision="rev-1", collected="2026-09-16T12:00:00Z"):
    return {
        "schemaVersion": "0.1",
        "id": identifier,
        "kind": kind,
        "subjectId": "SUBJECT-1",
        "subjectRevision": revision,
        "producerId": f"producer-{identifier}",
        "producerRole": "test-runner",
        "producerIndependenceGroup": group,
        "collectedAt": collected,
        "locator": f"evidence/{identifier}.json",
        "sha256": DIGEST,
        "assertions": ["The declared check completed."],
    }


def result(check_id, status, evidence_id, evaluator_group="verification", revision="rev-1"):
    return {
        "checkId": check_id,
        "checkVersion": "1.0.0",
        "status": status,
        "subjectId": "SUBJECT-1",
        "subjectRevision": revision,
        "subjectProducerIndependenceGroup": "implementation",
        "evaluatedAt": "2026-09-16T13:00:00Z",
        "evaluator": {
            "id": f"evaluator-{check_id}",
            "role": "verifier",
            "independenceGroup": evaluator_group,
        },
        "evidenceIds": [evidence_id],
    }


class EvidenceGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checks = load_check_library(sorted((ROOT / "checks").glob("*.json")))
        cls.gate = load_contract(ROOT / "gates" / "production-promotion.json")

    def evaluate(self, results, records, facts=None, exceptions=()):
        return evaluate_gate(
            self.gate,
            self.checks,
            results,
            records,
            facts or {"securityRelevant": False},
            "SUBJECT-1",
            "rev-1",
            "2026-09-16T14:00:00Z",
            exceptions,
        )

    def base_records(self):
        return [
            evidence("EVID-TEST", "test_result"),
            evidence("EVID-REVIEW", "review_disposition", group="review"),
        ]

    def base_results(self):
        return [
            result("CHECK-AUTOMATED-TESTS", "passed", "EVID-TEST"),
            result("CHECK-INDEPENDENT-REVIEW", "passed", "EVID-REVIEW"),
        ]

    def test_example_contracts_validate(self):
        validate_gate_contract(self.gate, self.checks)

    def test_gate_passes_with_admissible_required_checks(self):
        outcome = self.evaluate(self.base_results(), self.base_records())
        self.assertEqual(outcome.outcome, GateOutcome.PASSED)
        self.assertTrue(outcome.promotable)

    def test_missing_required_check_is_inconclusive(self):
        outcome = self.evaluate(self.base_results()[:1], self.base_records())
        self.assertEqual(outcome.outcome, GateOutcome.INCONCLUSIVE)
        self.assertIn("CHECK-INDEPENDENT-REVIEW", outcome.missing_checks)

    def test_failed_required_check_fails_gate(self):
        results = self.base_results()
        results[0]["status"] = "failed"
        outcome = self.evaluate(results, self.base_records())
        self.assertEqual(outcome.outcome, GateOutcome.FAILED)
        self.assertFalse(outcome.promotable)

    def test_stale_evidence_is_not_admissible(self):
        records = self.base_records()
        records[0]["collectedAt"] = "2026-09-14T00:00:00Z"
        outcome = self.evaluate(self.base_results(), records)
        self.assertEqual(outcome.outcome, GateOutcome.INCONCLUSIVE)
        self.assertIn("CHECK-AUTOMATED-TESTS", outcome.invalid_checks)

    def test_wrong_revision_evidence_is_not_admissible(self):
        records = self.base_records()
        records[0]["subjectRevision"] = "rev-old"
        outcome = self.evaluate(self.base_results(), records)
        self.assertEqual(outcome.outcome, GateOutcome.INCONCLUSIVE)

    def test_self_review_is_not_independent(self):
        results = self.base_results()
        results[1]["evaluator"]["independenceGroup"] = "implementation"
        outcome = self.evaluate(results, self.base_records())
        self.assertEqual(outcome.outcome, GateOutcome.INCONCLUSIVE)
        self.assertIn("CHECK-INDEPENDENT-REVIEW", outcome.invalid_checks)

    def test_security_check_activates_conditionally(self):
        outcome = self.evaluate(
            self.base_results(), self.base_records(), {"securityRelevant": True}
        )
        self.assertEqual(outcome.outcome, GateOutcome.INCONCLUSIVE)
        self.assertIn("CHECK-SECURITY-SCAN", outcome.missing_checks)

    def test_valid_bounded_exception_is_visible(self):
        results = self.base_results() + [
            result("CHECK-SECURITY-SCAN", "failed", "EVID-SCAN")
        ]
        records = self.base_records() + [evidence("EVID-SCAN", "scan_result")]
        exception = {
            "id": "EXC-1",
            "gateId": "GATE-PRODUCTION-PROMOTION",
            "checkId": "CHECK-SECURITY-SCAN",
            "subjectId": "SUBJECT-1",
            "subjectRevision": "rev-1",
            "authority": "risk_owner",
            "grantedBy": "person-1",
            "rationale": "Known bounded finding with compensating control.",
            "expiresAt": "2026-09-17T00:00:00Z",
        }
        outcome = self.evaluate(
            results, records, {"securityRelevant": True}, [exception]
        )
        self.assertEqual(outcome.outcome, GateOutcome.PASSED_WITH_EXCEPTION)
        self.assertEqual(outcome.accepted_exceptions, ("EXC-1",))

    def test_nonwaivable_failed_check_rejects_exception(self):
        results = self.base_results()
        results[0]["status"] = "failed"
        exception = {
            "id": "EXC-HARD",
            "gateId": "GATE-PRODUCTION-PROMOTION",
            "checkId": "CHECK-AUTOMATED-TESTS",
            "subjectId": "SUBJECT-1",
            "subjectRevision": "rev-1",
            "authority": "risk_owner",
            "grantedBy": "person-1",
            "rationale": "Attempt to bypass a hard control.",
            "expiresAt": "2026-09-17T00:00:00Z",
        }
        outcome = self.evaluate(results, self.base_records(), exceptions=[exception])
        self.assertEqual(outcome.outcome, GateOutcome.FAILED)
        self.assertEqual(outcome.accepted_exceptions, ())
        self.assertTrue(any("non-waivable" in reason for reason in outcome.reasons))

    def test_check_result_for_another_revision_is_inconclusive(self):
        results = self.base_results()
        results[0]["subjectRevision"] = "rev-old"
        outcome = self.evaluate(results, self.base_records())
        self.assertEqual(outcome.outcome, GateOutcome.INCONCLUSIVE)
        self.assertIn("CHECK-AUTOMATED-TESTS", outcome.invalid_checks)

    def test_hard_control_cannot_be_marked_waivable(self):
        invalid = copy.deepcopy(self.gate)
        invalid["checkRules"][0]["waivable"] = True
        with self.assertRaisesRegex(EvidenceGateError, "cannot be waivable"):
            validate_gate_contract(invalid, self.checks)

    def test_duplicate_check_results_fail_closed(self):
        duplicate = self.base_results()
        duplicate.append(copy.deepcopy(duplicate[0]))
        with self.assertRaisesRegex(EvidenceGateError, "Duplicate check result"):
            self.evaluate(duplicate, self.base_records())


if __name__ == "__main__":
    unittest.main()
