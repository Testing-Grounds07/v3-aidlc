import copy
import unittest
from pathlib import Path

from v3_aidlc.context_compiler import (
    ContextError,
    compile_context,
    load_contract,
    validate_context_item,
    validate_recipe,
)


ROOT = Path(__file__).parents[1]
NOW = "2026-09-16T12:00:00Z"


def item(identifier, kind, content, **overrides):
    value = {
        "schemaVersion": "0.1",
        "id": identifier,
        "revision": "1",
        "kind": kind,
        "sourceType": "canonical_state",
        "sourceRef": f"state:{identifier}",
        "sensitivity": "internal",
        "integrity": "authoritative",
        "projectId": "PRJ-1",
        "createdAt": "2026-09-16T10:00:00Z",
        "claimKey": identifier.lower(),
        "entityIds": [],
        "stages": [],
        "modes": [],
        "roles": [],
        "relevanceTags": ["feature-a"],
        "alwaysInclude": False,
        "content": content,
    }
    value.update(overrides)
    return value


def base_items():
    return [
        item("ITEM-OBJECTIVE", "objective", "Deliver feature A", alwaysInclude=True),
        item("ITEM-REQUIREMENT", "requirement", "Feature A must save records"),
        item("ITEM-CONSTRAINT", "constraint", "Do not change authentication", alwaysInclude=True),
        item("ITEM-TOOLS", "tool_contract", "Use only allowed filesystem and test tools", alwaysInclude=True),
    ]


def run(role="implementer"):
    return {
        "runId": "RUN-1",
        "projectId": "PRJ-1",
        "role": role,
        "entityIds": ["WP-1"],
        "stage": "implementation",
        "modes": ["MODE-IMPLEMENT"],
        "taskTags": ["feature-a"],
    }


class ContextCompilerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.implementation = load_contract(
            ROOT / "context-recipes" / "implementation.json"
        )
        cls.review = load_contract(
            ROOT / "context-recipes" / "independent-review.json"
        )

    def test_example_recipes_validate(self):
        validate_recipe(self.implementation)
        validate_recipe(self.review)

    def test_compiler_selects_required_relevant_context(self):
        candidates = base_items() + [
            item("ITEM-OTHER", "finding", "Unrelated finding", relevanceTags=["feature-b"])
        ]
        manifest = compile_context(self.implementation, run(), candidates, [], NOW)
        selected = {entry["id"] for entry in manifest.selected_items}
        self.assertEqual(selected, {entry["id"] for entry in base_items()})
        self.assertTrue(any(x.item_id == "ITEM-OTHER" for x in manifest.exclusions))

    def test_higher_authority_wins_same_claim(self):
        candidates = base_items() + [
            item(
                "ITEM-LOW",
                "constraint",
                "Authentication may change",
                claimKey="auth-change",
                sourceType="liaison_summary",
                sourceRef="conversation:1",
                integrity="unverified",
            ),
            item(
                "ITEM-HIGH",
                "constraint",
                "Authentication must not change",
                claimKey="auth-change",
                sourceType="organization_policy",
                sourceRef="policy:1",
            ),
        ]
        manifest = compile_context(self.implementation, run(), candidates, [], NOW)
        selected = {entry["id"] for entry in manifest.selected_items}
        self.assertIn("ITEM-HIGH", selected)
        self.assertNotIn("ITEM-LOW", selected)

    def test_equal_authority_conflict_fails_closed(self):
        candidates = base_items() + [
            item("ITEM-C1", "constraint", "Use blue", claimKey="color"),
            item("ITEM-C2", "constraint", "Use green", claimKey="color"),
        ]
        with self.assertRaisesRegex(ContextError, "conflict"):
            compile_context(self.implementation, run(), candidates, [], NOW)

    def test_confidential_context_requires_exact_grant(self):
        confidential = item(
            "ITEM-CONFIDENTIAL",
            "architecture",
            "Private system topology",
            sensitivity="confidential",
        )
        without = compile_context(
            self.implementation, run(), base_items() + [confidential], [], NOW
        )
        self.assertNotIn(
            "ITEM-CONFIDENTIAL", {x["id"] for x in without.selected_items}
        )
        grant = {
            "id": "GRANT-1",
            "projectId": "PRJ-1",
            "recipientRole": "implementer",
            "purpose": "Implement feature A",
            "grantedBy": "project-lead",
            "authority": "project_policy",
            "expiresAt": "2026-09-17T00:00:00Z",
            "itemIds": ["ITEM-CONFIDENTIAL"],
            "runIds": ["RUN-1"],
        }
        with_grant = compile_context(
            self.implementation, run(), base_items() + [confidential], [grant], NOW
        )
        self.assertIn(
            "ITEM-CONFIDENTIAL", {x["id"] for x in with_grant.selected_items}
        )

    def test_expired_grant_does_not_disclose(self):
        confidential = item(
            "ITEM-CONFIDENTIAL",
            "architecture",
            "Private system topology",
            sensitivity="confidential",
        )
        grant = {
            "id": "GRANT-1",
            "projectId": "PRJ-1",
            "recipientRole": "implementer",
            "purpose": "Implement feature A",
            "grantedBy": "project-lead",
            "authority": "project_policy",
            "expiresAt": "2026-09-16T11:00:00Z",
            "itemIds": ["ITEM-CONFIDENTIAL"],
            "runIds": ["RUN-1"],
        }
        manifest = compile_context(
            self.implementation, run(), base_items() + [confidential], [grant], NOW
        )
        self.assertNotIn(
            "ITEM-CONFIDENTIAL", {x["id"] for x in manifest.selected_items}
        )

    def test_grant_for_another_run_does_not_disclose(self):
        confidential = item(
            "ITEM-CONFIDENTIAL",
            "architecture",
            "Private system topology",
            sensitivity="confidential",
        )
        grant = {
            "id": "GRANT-OTHER-RUN",
            "projectId": "PRJ-1",
            "recipientRole": "implementer",
            "purpose": "A different task",
            "grantedBy": "project-lead",
            "authority": "project_policy",
            "expiresAt": "2026-09-17T00:00:00Z",
            "itemIds": ["ITEM-CONFIDENTIAL"],
            "runIds": ["RUN-OTHER"],
        }
        manifest = compile_context(
            self.implementation, run(), base_items() + [confidential], [grant], NOW
        )
        self.assertNotIn(
            "ITEM-CONFIDENTIAL", {x["id"] for x in manifest.selected_items}
        )

    def test_secret_value_cannot_be_put_in_context(self):
        invalid = item(
            "ITEM-SECRET",
            "constraint",
            "actual-password",
            sensitivity="secret",
        )
        with self.assertRaisesRegex(ContextError, "references"):
            validate_context_item(invalid)

    def test_secret_reference_can_be_scoped_without_secret_value(self):
        secret = item(
            "ITEM-SECRET",
            "secret_reference",
            "placeholder",
            sensitivity="secret",
        )
        del secret["content"]
        secret["reference"] = "secret-manager://project/service-token"
        grant = {
            "id": "GRANT-SECRET",
            "projectId": "PRJ-1",
            "recipientRole": "implementer",
            "purpose": "Run authorized integration test",
            "grantedBy": "project-lead",
            "authority": "project_policy",
            "expiresAt": "2026-09-17T00:00:00Z",
            "itemIds": ["ITEM-SECRET"],
            "runIds": ["RUN-1"],
        }
        manifest = compile_context(
            self.implementation, run(), base_items() + [secret], [grant], NOW
        )
        selected = next(x for x in manifest.selected_items if x["id"] == "ITEM-SECRET")
        self.assertIsNone(selected["content"])
        self.assertTrue(selected["reference"].startswith("secret-manager://"))

    def test_required_kind_missing_fails_closed(self):
        with self.assertRaisesRegex(ContextError, "Required context kinds"):
            compile_context(self.implementation, run(), base_items()[:-1], [], NOW)

    def test_context_budget_cannot_silently_drop_required_kind(self):
        recipe = copy.deepcopy(self.implementation)
        recipe["maxItems"] = 3
        with self.assertRaisesRegex(ContextError, "Required context kinds"):
            compile_context(recipe, run(), base_items(), [], NOW)

    def test_same_inputs_produce_same_manifest_digest(self):
        first = compile_context(self.implementation, run(), base_items(), [], NOW)
        second = compile_context(self.implementation, run(), base_items(), [], NOW)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.manifest_id, second.manifest_id)

    def test_reviewer_recipe_is_read_only_and_excludes_assumptions(self):
        self.assertNotIn("filesystem.write", self.review["toolAllowlist"])
        self.assertNotIn("assumption", self.review["allowedKinds"])
        self.assertNotIn("liaison_summary", self.review["allowedSources"])

    def test_liaison_summary_cannot_claim_authoritative_integrity(self):
        invalid = item(
            "ITEM-SUMMARY",
            "constraint",
            "Summary",
            sourceType="liaison_summary",
            sourceRef="conversation:1",
            integrity="authoritative",
        )
        with self.assertRaisesRegex(ContextError, "cannot be authoritative"):
            validate_context_item(invalid)


if __name__ == "__main__":
    unittest.main()
