import copy
import json
import unittest
from pathlib import Path

from v3_aidlc.agent_adapters import (
    AdapterError,
    NegotiationDecision,
    build_dispatch,
    canonical_digest,
    negotiate_capabilities,
    normalize_provider_result,
    select_adapter,
    validate_capability_profile,
    validate_dispatch,
    validate_run_result,
)


def profile(adapter_id="adapter-a", **overrides):
    value = {
        "schemaVersion": "0.1",
        "profileId": f"profile-{adapter_id}",
        "adapterId": adapter_id,
        "adapterVersion": "1.0.0",
        "provider": "provider-a",
        "model": "model-a",
        "status": "available",
        "roles": ["implementer", "reviewer"],
        "capabilities": ["code_edit", "test_execution", "structured_response"],
        "modalities": ["text"],
        "tools": ["filesystem", "shell"],
        "networkHosts": [],
        "maxContextBytes": 100_000,
        "maxOutputBytes": 20_000,
        "maxConcurrentRuns": 2,
        "maxSensitivity": "confidential",
        "structuredOutput": True,
        "streaming": False,
        "externalSideEffects": False,
        "idempotentInvocation": True,
    }
    value.update(overrides)
    return value


def request(**overrides):
    value = {
        "schemaVersion": "0.1",
        "runId": "RUN-1",
        "projectId": "PRJ-1",
        "workPackageId": "WP-1",
        "role": "implementer",
        "objective": "Implement and test the bounded change.",
        "contextManifestId": "CTX-1",
        "contextManifestDigest": "a" * 64,
        "contextBytes": 40_000,
        "sensitivity": "internal",
        "requiredCapabilities": ["code_edit", "test_execution"],
        "requiredModalities": ["text"],
        "requiredTools": ["filesystem", "shell"],
        "requiredNetworkHosts": [],
        "structuredOutputRequired": True,
        "externalSideEffectPossible": False,
        "maxOutputBytes": 10_000,
        "completionCriteria": ["change-implemented", "tests-pass"],
        "authorizationDecision": "auto_proceed_and_record",
        "attempt": 1,
        "idempotencyKey": "run:1:attempt:1",
    }
    value.update(overrides)
    return value


def raw_result(**overrides):
    value = {
        "startedAt": "2026-09-17T01:00:00Z",
        "finishedAt": "2026-09-17T01:02:00Z",
        "status": "completed",
        "summary": "Implemented and verified the requested change.",
        "artifactIds": ["ART-1"],
        "evidenceIds": ["EVID-1"],
        "satisfiedCriteria": ["change-implemented", "tests-pass"],
        "findingIds": [],
        "externalEffects": [],
        "usage": {"inputUnits": 1200, "outputUnits": 300},
    }
    value.update(overrides)
    return value


class AgentAdapterTest(unittest.TestCase):
    def test_compatible_runner_is_accepted(self):
        result = negotiate_capabilities(request(), profile())
        self.assertEqual(result.decision, NegotiationDecision.ACCEPTED)
        self.assertEqual(result.reasons, ())

    def test_missing_capability_is_rejected_with_exact_reason(self):
        result = negotiate_capabilities(
            request(requiredCapabilities=["code_edit", "vision"]), profile()
        )
        self.assertEqual(result.decision, NegotiationDecision.REJECTED)
        self.assertIn("missing capability: vision", result.reasons)

    def test_unknown_capability_is_not_inferred_from_provider_name(self):
        capable_sounding = profile(provider="all-powerful", capabilities=[])
        result = negotiate_capabilities(request(), capable_sounding)
        self.assertEqual(result.decision, NegotiationDecision.REJECTED)

    def test_user_decision_required_cannot_dispatch(self):
        result = negotiate_capabilities(
            request(authorizationDecision="user_decision_required"), profile()
        )
        self.assertIn("does not permit dispatch", result.reasons[0])

    def test_sensitivity_clearance_is_enforced(self):
        result = negotiate_capabilities(
            request(sensitivity="restricted"), profile(maxSensitivity="confidential")
        )
        self.assertIn("sensitivity", " ".join(result.reasons))

    def test_retry_requires_idempotent_invocation(self):
        result = negotiate_capabilities(
            request(attempt=2), profile(idempotentInvocation=False)
        )
        self.assertIn("retry", " ".join(result.reasons))

    def test_external_effect_requires_explicit_support(self):
        result = negotiate_capabilities(
            request(externalSideEffectPossible=True), profile()
        )
        self.assertIn("external side effects", " ".join(result.reasons))

    def test_unavailable_and_degraded_runners_are_not_selected(self):
        for status in ("unavailable", "degraded"):
            with self.subTest(status=status):
                result = negotiate_capabilities(request(), profile(status=status))
                self.assertEqual(result.decision, NegotiationDecision.REJECTED)

    def test_selection_is_least_privilege_then_stable(self):
        broad = profile(
            "adapter-broad", maxSensitivity="secret", maxContextBytes=1_000_000
        )
        narrow = profile(
            "adapter-narrow", maxSensitivity="internal", maxContextBytes=50_000
        )
        selected, results = select_adapter(request(), [broad, narrow])
        self.assertEqual(selected["adapterId"], "adapter-narrow")
        self.assertEqual(len(results), 2)

    def test_no_compatible_adapter_reports_every_rejection(self):
        with self.assertRaisesRegex(AdapterError, "adapter-a.*missing tool"):
            select_adapter(request(requiredTools=["browser"]), [profile()])

    def test_duplicate_adapter_identity_is_rejected(self):
        with self.assertRaisesRegex(AdapterError, "duplicate adapterId"):
            select_adapter(request(), [profile(), profile(profileId="different")])

    def test_dispatch_pins_profile_context_request_and_lease(self):
        run_request = request()
        runner = profile()
        dispatch = build_dispatch(run_request, runner, lease_id="LEASE-1")
        self.assertEqual(dispatch["profileDigest"], canonical_digest(runner))
        self.assertEqual(dispatch["requestDigest"], canonical_digest(run_request))
        self.assertEqual(dispatch["contextManifestDigest"], "a" * 64)
        self.assertEqual(dispatch["leaseId"], "LEASE-1")
        validate_dispatch(dispatch)

    def test_tampered_dispatch_is_rejected(self):
        dispatch = build_dispatch(request(), profile(), lease_id="LEASE-1")
        dispatch["request"]["objective"] = "A different task"
        with self.assertRaisesRegex(AdapterError, "request digest"):
            validate_dispatch(dispatch)

    def test_normalized_result_is_bound_to_dispatch(self):
        dispatch = build_dispatch(request(), profile(), lease_id="LEASE-1")
        result = normalize_provider_result(
            raw_result(), dispatch, provider_result_ref="provider-result:1"
        )
        validate_run_result(result, dispatch)
        self.assertEqual(result["dispatchDigest"], dispatch["dispatchDigest"])
        self.assertNotIn("providerPayload", result)

    def test_result_from_different_context_is_rejected(self):
        dispatch = build_dispatch(request(), profile(), lease_id="LEASE-1")
        result = normalize_provider_result(
            raw_result(), dispatch, provider_result_ref="provider-result:1"
        )
        changed = copy.deepcopy(result)
        changed["contextManifestId"] = "CTX-OTHER"
        with self.assertRaisesRegex(AdapterError, "contextManifestId"):
            validate_run_result(changed, dispatch)

    def test_completion_requires_every_criterion_and_evidence(self):
        dispatch = build_dispatch(request(), profile(), lease_id="LEASE-1")
        with self.assertRaisesRegex(AdapterError, "missing criteria"):
            normalize_provider_result(
                raw_result(satisfiedCriteria=["tests-pass"]),
                dispatch,
                provider_result_ref="provider-result:1",
            )
        with self.assertRaisesRegex(AdapterError, "requires evidence"):
            normalize_provider_result(
                raw_result(evidenceIds=[]),
                dispatch,
                provider_result_ref="provider-result:2",
            )

    def test_non_completed_run_cannot_claim_success(self):
        dispatch = build_dispatch(request(), profile(), lease_id="LEASE-1")
        with self.assertRaisesRegex(AdapterError, "cannot claim"):
            normalize_provider_result(
                raw_result(status="failed"),
                dispatch,
                provider_result_ref="provider-result:1",
            )

    def test_result_time_cannot_run_backwards(self):
        dispatch = build_dispatch(request(), profile(), lease_id="LEASE-1")
        with self.assertRaisesRegex(AdapterError, "earlier"):
            normalize_provider_result(
                raw_result(
                    startedAt="2026-09-17T01:02:00Z",
                    finishedAt="2026-09-17T01:00:00Z",
                ),
                dispatch,
                provider_result_ref="provider-result:1",
            )

    def test_unauthorized_external_effect_is_rejected(self):
        dispatch = build_dispatch(request(), profile(), lease_id="LEASE-1")
        effect = {
            "effectKey": "deploy:1",
            "effectType": "deployment",
            "status": "succeeded",
            "observationRef": "deployment:1",
        }
        with self.assertRaisesRegex(AdapterError, "not authorized"):
            normalize_provider_result(
                raw_result(externalEffects=[effect]),
                dispatch,
                provider_result_ref="provider-result:1",
            )

    def test_all_adapter_schemas_are_valid_json(self):
        schema_dir = Path(__file__).parents[1] / "schemas"
        for name in (
            "capability-profile.schema.json",
            "agent-run-request.schema.json",
            "agent-run-dispatch.schema.json",
            "agent-run-result.schema.json",
        ):
            with self.subTest(name=name):
                json.loads((schema_dir / name).read_text(encoding="utf-8"))

    def test_profile_rejects_duplicate_declared_capabilities(self):
        with self.assertRaisesRegex(AdapterError, "duplicates"):
            validate_capability_profile(profile(capabilities=["code_edit", "code_edit"]))


if __name__ == "__main__":
    unittest.main()
