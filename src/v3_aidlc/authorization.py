"""Deterministic adaptive-authorization policy evaluation for V3-AIDLC."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


SCOPES = {"organization", "project", "route", "workstream", "mode", "target"}
PREDICATE_KEYS = {"equals", "in"}


class AuthorizationError(ValueError):
    """Raised when a policy is invalid or cannot safely be evaluated."""


class AuthorizationDecision(str, Enum):
    AUTO_PROCEED = "auto_proceed"
    AUTO_PROCEED_AND_RECORD = "auto_proceed_and_record"
    AUTO_PROCEED_WITHIN_BUDGET = "auto_proceed_within_budget"
    USER_DECISION_REQUIRED = "user_decision_required"
    BLOCKED = "blocked"


DECISION_STRICTNESS = {
    AuthorizationDecision.AUTO_PROCEED: 0,
    AuthorizationDecision.AUTO_PROCEED_AND_RECORD: 1,
    AuthorizationDecision.AUTO_PROCEED_WITHIN_BUDGET: 2,
    AuthorizationDecision.USER_DECISION_REQUIRED: 3,
    AuthorizationDecision.BLOCKED: 4,
}


@dataclass(frozen=True)
class RuleMatch:
    policy_id: str
    policy_version: str
    rule_id: str
    decision: AuthorizationDecision
    explanation: str
    priority: int
    budget_status: str | None = None


@dataclass(frozen=True)
class AuthorizationResult:
    decision: AuthorizationDecision
    explanation: str
    controlling_rules: tuple[str, ...]
    matches: tuple[RuleMatch, ...]
    record_required: bool


def load_policy(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuthorizationError(f"Cannot load policy {path}: {error}") from error
    if not isinstance(value, dict):
        raise AuthorizationError(f"Policy {path} must contain a JSON object")
    return value


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise AuthorizationError(f"{key} must be a non-empty string")
    return result


def _validate_predicate(predicate: Any) -> None:
    if not isinstance(predicate, dict):
        raise AuthorizationError("Each predicate must be an object")
    _required_string(predicate, "fact")
    operators = PREDICATE_KEYS.intersection(predicate)
    if len(operators) != 1:
        raise AuthorizationError("Each predicate must use exactly one operator")
    if set(predicate) - {"fact"} - PREDICATE_KEYS:
        raise AuthorizationError("Predicate contains unsupported fields")
    if "in" in predicate and (
        not isinstance(predicate["in"], list) or not predicate["in"]
    ):
        raise AuthorizationError("Predicate 'in' must be a non-empty array")


def validate_policy(policy: dict[str, Any]) -> None:
    _required_string(policy, "id")
    _required_string(policy, "version")
    _required_string(policy, "title")
    if policy.get("scope") not in SCOPES:
        raise AuthorizationError(f"Unknown policy scope: {policy.get('scope')}")
    try:
        AuthorizationDecision(policy.get("defaultDecision"))
    except ValueError as error:
        raise AuthorizationError("defaultDecision is invalid") from error

    rules = policy.get("rules")
    if not isinstance(rules, list) or not rules:
        raise AuthorizationError("rules must be a non-empty array")
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise AuthorizationError("Each rule must be an object")
        rule_id = _required_string(rule, "id")
        if rule_id in seen:
            raise AuthorizationError(f"Duplicate rule ID: {rule_id}")
        seen.add(rule_id)
        _required_string(rule, "explanation")
        if not isinstance(rule.get("priority"), int):
            raise AuthorizationError(f"Rule {rule_id} priority must be an integer")
        try:
            decision = AuthorizationDecision(rule.get("decision"))
        except ValueError as error:
            raise AuthorizationError(f"Rule {rule_id} has an invalid decision") from error
        predicates = rule.get("whenAll")
        if not isinstance(predicates, list) or not predicates:
            raise AuthorizationError(f"Rule {rule_id} must define whenAll")
        for predicate in predicates:
            _validate_predicate(predicate)

        budgets = rule.get("budgets", [])
        if decision is AuthorizationDecision.AUTO_PROCEED_WITHIN_BUDGET and not budgets:
            raise AuthorizationError(
                f"Rule {rule_id} uses a budgeted decision without budgets"
            )
        if budgets and decision is not AuthorizationDecision.AUTO_PROCEED_WITHIN_BUDGET:
            raise AuthorizationError(
                f"Rule {rule_id} defines budgets without a budgeted decision"
            )
        if not isinstance(budgets, list):
            raise AuthorizationError(f"Rule {rule_id} budgets must be an array")
        for budget in budgets:
            if not isinstance(budget, dict):
                raise AuthorizationError("Each budget must be an object")
            _required_string(budget, "fact")
            maximum = budget.get("maximum")
            if not isinstance(maximum, (int, float)) or isinstance(maximum, bool):
                raise AuthorizationError("Budget maximum must be numeric")
        if budgets and rule.get("onBudgetExceeded") != "user_decision_required":
            raise AuthorizationError(
                f"Rule {rule_id} must escalate when its budget is exceeded"
            )


def _matches(predicate: dict[str, Any], facts: dict[str, Any]) -> bool:
    fact = predicate["fact"]
    if fact not in facts:
        return False
    actual = facts[fact]
    if "equals" in predicate:
        return actual == predicate["equals"]
    return actual in predicate["in"]


def _evaluate_budget(
    budgets: list[dict[str, Any]], facts: dict[str, Any]
) -> tuple[bool, str]:
    statuses: list[str] = []
    for budget in budgets:
        fact = budget["fact"]
        if fact not in facts:
            return False, f"budget fact {fact} is missing"
        actual = facts[fact]
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return False, f"budget fact {fact} is not numeric"
        maximum = budget["maximum"]
        statuses.append(f"{fact}={actual}/{maximum}")
        if actual > maximum:
            return False, ", ".join(statuses) + " (exceeded)"
    return True, ", ".join(statuses) + " (within budget)"


def evaluate_authorization(
    policies: Iterable[dict[str, Any]], facts: dict[str, Any]
) -> AuthorizationResult:
    """Evaluate every applicable rule; the strictest matching rule wins."""

    policy_list = list(policies)
    if not policy_list:
        raise AuthorizationError("At least one authorization policy is required")

    matches: list[RuleMatch] = []
    defaults: list[tuple[dict[str, Any], AuthorizationDecision]] = []
    for policy in policy_list:
        validate_policy(policy)
        defaults.append((policy, AuthorizationDecision(policy["defaultDecision"])))
        for rule in policy["rules"]:
            if not all(_matches(predicate, facts) for predicate in rule["whenAll"]):
                continue
            decision = AuthorizationDecision(rule["decision"])
            budget_status = None
            if decision is AuthorizationDecision.AUTO_PROCEED_WITHIN_BUDGET:
                within_budget, budget_status = _evaluate_budget(
                    rule.get("budgets", []), facts
                )
                if not within_budget:
                    decision = AuthorizationDecision.USER_DECISION_REQUIRED
            matches.append(
                RuleMatch(
                    policy_id=policy["id"],
                    policy_version=policy["version"],
                    rule_id=rule["id"],
                    decision=decision,
                    explanation=rule["explanation"],
                    priority=rule["priority"],
                    budget_status=budget_status,
                )
            )

    if not matches:
        strictest_default = max(defaults, key=lambda item: DECISION_STRICTNESS[item[1]])
        policy, decision = strictest_default
        return AuthorizationResult(
            decision=decision,
            explanation=(
                f"No authorization rule matched; policy {policy['id']} applies its "
                f"fail-closed default."
            ),
            controlling_rules=(f"{policy['id']}:default",),
            matches=(),
            record_required=decision is not AuthorizationDecision.AUTO_PROCEED,
        )

    strictness = max(DECISION_STRICTNESS[item.decision] for item in matches)
    controlling = [
        item for item in matches if DECISION_STRICTNESS[item.decision] == strictness
    ]
    controlling.sort(key=lambda item: (-item.priority, item.policy_id, item.rule_id))
    decision = controlling[0].decision
    reasons = []
    for item in controlling:
        reason = item.explanation
        if item.budget_status:
            reason += f" ({item.budget_status})"
        reasons.append(reason)
    return AuthorizationResult(
        decision=decision,
        explanation=" ".join(reasons),
        controlling_rules=tuple(
            f"{item.policy_id}:{item.rule_id}" for item in controlling
        ),
        matches=tuple(matches),
        record_required=decision is not AuthorizationDecision.AUTO_PROCEED,
    )
