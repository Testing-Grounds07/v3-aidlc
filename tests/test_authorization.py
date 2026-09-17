import copy
import unittest
from pathlib import Path

from v3_aidlc.authorization import (
    AuthorizationDecision,
    AuthorizationError,
    evaluate_authorization,
    load_policy,
    validate_policy,
)


ROOT = Path(__file__).parents[1]


class AuthorizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(ROOT / "policies" / "governed-development.json")

    def test_baseline_policy_validates(self) -> None:
        validate_policy(self.policy)

    def test_routine_local_work_proceeds_automatically(self) -> None:
        result = evaluate_authorization(
            [self.policy],
            {
                "actionType": "test",
                "impact": "local_reversible",
                "scopeChange": "none",
                "waivesHardControl": False,
                "hasRequiredPermission": True,
            },
        )
        self.assertEqual(result.decision, AuthorizationDecision.AUTO_PROCEED)
        self.assertFalse(result.record_required)

    def test_material_product_change_overrides_routine_rule(self) -> None:
        result = evaluate_authorization(
            [self.policy],
            {
                "actionType": "implement",
                "impact": "local_reversible",
                "scopeChange": "none",
                "changesProductIntent": True,
                "waivesHardControl": False,
                "hasRequiredPermission": True,
            },
        )
        self.assertEqual(
            result.decision, AuthorizationDecision.USER_DECISION_REQUIRED
        )
        self.assertIn("RULE-ASK-MATERIAL-PRODUCT-CHANGE", result.controlling_rules[0])

    def test_hard_control_waiver_is_blocked(self) -> None:
        result = evaluate_authorization(
            [self.policy],
            {
                "actionType": "implement",
                "impact": "local_reversible",
                "scopeChange": "none",
                "waivesHardControl": True,
                "hasRequiredPermission": True,
            },
        )
        self.assertEqual(result.decision, AuthorizationDecision.BLOCKED)

    def test_repair_proceeds_inside_budget(self) -> None:
        result = evaluate_authorization(
            [self.policy],
            {
                "actionType": "repair",
                "impact": "local_reversible",
                "repairAttempt": 2,
                "costUnits": 8,
                "waivesHardControl": False,
                "hasRequiredPermission": True,
            },
        )
        self.assertEqual(
            result.decision, AuthorizationDecision.AUTO_PROCEED_WITHIN_BUDGET
        )
        self.assertIn("within budget", result.explanation)

    def test_repair_escalates_when_budget_is_exceeded(self) -> None:
        result = evaluate_authorization(
            [self.policy],
            {
                "actionType": "repair",
                "impact": "local_reversible",
                "repairAttempt": 3,
                "costUnits": 8,
                "waivesHardControl": False,
                "hasRequiredPermission": True,
            },
        )
        self.assertEqual(
            result.decision, AuthorizationDecision.USER_DECISION_REQUIRED
        )
        self.assertIn("exceeded", result.explanation)

    def test_missing_budget_fact_fails_closed(self) -> None:
        result = evaluate_authorization(
            [self.policy],
            {
                "actionType": "repair",
                "impact": "local_reversible",
                "repairAttempt": 1,
                "waivesHardControl": False,
                "hasRequiredPermission": True,
            },
        )
        self.assertEqual(
            result.decision, AuthorizationDecision.USER_DECISION_REQUIRED
        )
        self.assertIn("missing", result.explanation)

    def test_unknown_action_uses_fail_closed_default(self) -> None:
        result = evaluate_authorization(
            [self.policy],
            {"actionType": "invented_action", "hasRequiredPermission": True},
        )
        self.assertEqual(
            result.decision, AuthorizationDecision.USER_DECISION_REQUIRED
        )
        self.assertIn("fail-closed", result.explanation)

    def test_missing_permission_fact_does_not_authorize_routine_work(self) -> None:
        result = evaluate_authorization(
            [self.policy],
            {
                "actionType": "test",
                "impact": "local_reversible",
                "scopeChange": "none",
            },
        )
        self.assertEqual(
            result.decision, AuthorizationDecision.USER_DECISION_REQUIRED
        )

    def test_delegated_production_promotion_requires_passed_gates(self) -> None:
        base = {
            "actionType": "promote",
            "targetEnvironment": "production",
            "usesCredentials": True,
            "standingDelegation": True,
            "hasRequiredPermission": True,
            "waivesHardControl": False,
        }
        without_gates = evaluate_authorization([self.policy], base)
        with_gates = evaluate_authorization(
            [self.policy], {**base, "requiredGatesPassed": True}
        )
        self.assertEqual(
            without_gates.decision,
            AuthorizationDecision.USER_DECISION_REQUIRED,
        )
        self.assertEqual(
            with_gates.decision,
            AuthorizationDecision.AUTO_PROCEED_AND_RECORD,
        )
        self.assertIn(
            "POL-GOVERNED-DEVELOPMENT:RULE-RECORD-DELEGATED-PRODUCTION-PROMOTION",
            with_gates.controlling_rules,
        )

    def test_stricter_inherited_policy_wins(self) -> None:
        project_policy = {
            "schemaVersion": "0.1",
            "id": "POL-PROJECT-ASSURED",
            "version": "0.1.0",
            "title": "Assured project override",
            "scope": "project",
            "defaultDecision": "user_decision_required",
            "rules": [
                {
                    "id": "RULE-ASK-ALL-IMPLEMENTATION",
                    "priority": 700,
                    "decision": "user_decision_required",
                    "whenAll": [{"fact": "actionType", "equals": "implement"}],
                    "explanation": "This assured project requires implementation approval."
                }
            ]
        }
        result = evaluate_authorization(
            [self.policy, project_policy],
            {
                "actionType": "implement",
                "impact": "local_reversible",
                "scopeChange": "none",
                "waivesHardControl": False,
                "hasRequiredPermission": True,
            },
        )
        self.assertEqual(
            result.decision, AuthorizationDecision.USER_DECISION_REQUIRED
        )
        self.assertIn("POL-PROJECT-ASSURED", result.controlling_rules[0])

    def test_budget_on_non_budget_decision_is_invalid(self) -> None:
        invalid = copy.deepcopy(self.policy)
        invalid["rules"][-1]["budgets"] = [{"fact": "costUnits", "maximum": 1}]
        with self.assertRaisesRegex(AuthorizationError, "without a budgeted"):
            validate_policy(invalid)

    def test_budgeted_decision_requires_a_budget(self) -> None:
        invalid = copy.deepcopy(self.policy)
        budgeted = next(
            rule
            for rule in invalid["rules"]
            if rule["id"] == "RULE-BUDGETED-REPAIR"
        )
        del budgeted["budgets"]
        with self.assertRaisesRegex(AuthorizationError, "without budgets"):
            validate_policy(invalid)


if __name__ == "__main__":
    unittest.main()
