import copy
import json
import unittest
from pathlib import Path

from v3_aidlc.security import (
    SecurityDecision,
    SecurityError,
    assessment_to_dict,
    assess_security,
    build_containment_plan,
    validate_credential_lease,
    validate_containment_plan,
    verify_artifact,
)


NOW = "2026-09-17T12:00:00Z"


def request(**overrides):
    value = {
        "runId": "RUN-1",
        "projectId": "PRJ-1",
        "riskTier": "moderate",
        "minimumProvenance": "L1",
        "executesRetrievedContent": False,
        "externalSideEffectPossible": False,
        "requestedToolActions": [
            {"tool": "filesystem", "operation": "write", "resource": "workspace:src"}
        ],
        "requestedCredentials": [],
        "requestedNetworkHosts": [],
    }
    value.update(overrides)
    return value


def content(trust="governed", **overrides):
    value = {
        "id": "CONTENT-1",
        "source": "project:requirements",
        "digest": "a" * 64,
        "trustLevel": trust,
        "scannedAt": NOW,
        "activeContent": False,
        "containsInstructions": False,
        "usedAsAuthority": trust == "trusted_control",
        "signals": [],
    }
    value.update(overrides)
    return value


def tool_grant(**overrides):
    value = {
        "grantId": "GRANT-1",
        "runId": "RUN-1",
        "tool": "filesystem",
        "operations": ["read", "write"],
        "resources": ["workspace:src"],
        "networkHosts": [],
        "issuedAt": "2026-09-17T11:00:00Z",
        "expiresAt": "2026-09-17T13:00:00Z",
        "grantedBy": "project-lead",
        "revoked": False,
    }
    value.update(overrides)
    return value


def credential_lease(**overrides):
    value = {
        "leaseId": "CRED-1",
        "runId": "RUN-1",
        "secretRef": "vault://project/service-token",
        "audience": "api.example.com",
        "scopes": ["records.read"],
        "issuedAt": "2026-09-17T11:55:00Z",
        "expiresAt": "2026-09-17T12:05:00Z",
        "brokerId": "credential-broker",
        "oneTime": True,
        "renewable": False,
        "revoked": False,
    }
    value.update(overrides)
    return value


def dependency(**overrides):
    value = {
        "name": "safe-package",
        "version": "1.2.3",
        "source": "registry.example.com/safe-package",
        "digest": "b" * 64,
        "status": "approved",
        "signatureStatus": "verified",
        "provenanceLevel": "L2",
        "vulnerabilityStatus": "clear",
        "sbomRef": "sbom:safe-package:1.2.3",
    }
    value.update(overrides)
    return value


def sandbox(**overrides):
    value = {
        "sandboxId": "SANDBOX-1",
        "runId": "RUN-1",
        "ephemeral": True,
        "processIsolation": True,
        "cleanupOnExit": True,
        "telemetry": True,
        "workspaceAccess": "scoped_write",
        "networkPolicy": "deny_all",
        "networkHosts": [],
        "secretAccess": "none",
    }
    value.update(overrides)
    return value


def attestation(**overrides):
    value = {
        "attestationId": "ATT-1",
        "artifactId": "ART-1",
        "artifactDigest": "c" * 64,
        "subjectRevision": "rev-1",
        "producerRunId": "RUN-1",
        "builderId": "builder-1",
        "buildType": "https://example.com/build/v1",
        "provenanceLevel": "L2",
        "signatureStatus": "verified",
        "issuedAt": NOW,
        "materials": [{"uri": "git:repo@rev-1", "digest": "d" * 64}],
    }
    value.update(overrides)
    return value


def assess(req=None, contents=None, grants=None, leases=None, deps=None, box=None):
    return assess_security(
        req or request(),
        contents if contents is not None else [content()],
        grants if grants is not None else [tool_grant()],
        leases if leases is not None else [],
        deps if deps is not None else [dependency()],
        box or sandbox(),
        now=NOW,
    )


class SecurityTest(unittest.TestCase):
    def test_governed_bounded_run_is_allowed(self):
        result = assess()
        self.assertEqual(result.decision, SecurityDecision.ALLOW)
        self.assertIn("bind-actions-to-run", result.required_controls)
        payload = assessment_to_dict(result)
        self.assertEqual(payload["decision"], "allow")
        self.assertEqual(payload["schemaVersion"], "0.1")

    def test_untrusted_content_is_data_not_authority(self):
        with self.assertRaisesRegex(SecurityError, "only trusted control"):
            assess(contents=[content("untrusted", usedAsAuthority=True)])

    def test_untrusted_content_runs_only_in_isolation(self):
        result = assess(contents=[content("untrusted")])
        self.assertEqual(result.decision, SecurityDecision.ALLOW_ISOLATED)
        self.assertIn("no-authority-from-content", result.required_controls)

    def test_prompt_injection_signal_requires_review(self):
        result = assess(
            contents=[
                content(
                    "untrusted",
                    containsInstructions=True,
                    signals=["prompt_injection"],
                )
            ]
        )
        self.assertEqual(result.decision, SecurityDecision.REVIEW_REQUIRED)
        self.assertIn("treat-retrieved-instructions-as-data", result.required_controls)

    def test_serious_signal_triggers_containment(self):
        result = assess(
            contents=[content("untrusted", signals=["data_exfiltration"])]
        )
        self.assertEqual(result.decision, SecurityDecision.CONTAIN)

    def test_untrusted_active_content_requires_sealed_sandbox(self):
        result = assess(
            req=request(executesRetrievedContent=True),
            contents=[content("untrusted", activeContent=True)],
            box=sandbox(networkPolicy="allowlist", networkHosts=["example.com"]),
        )
        self.assertEqual(result.decision, SecurityDecision.BLOCK)
        self.assertIn("sealed ephemeral sandbox", " ".join(result.reasons))

    def test_untrusted_active_content_can_run_in_sealed_sandbox(self):
        result = assess(
            req=request(executesRetrievedContent=True),
            contents=[content("untrusted", activeContent=True)],
        )
        self.assertEqual(result.decision, SecurityDecision.ALLOW_ISOLATED)

    def test_missing_exact_tool_grant_blocks(self):
        result = assess(grants=[tool_grant(resources=["workspace:docs"])])
        self.assertEqual(result.decision, SecurityDecision.BLOCK)
        self.assertIn("missing exact tool grant", result.reasons[0])

    def test_expired_or_revoked_tool_grant_blocks(self):
        for grant in (
            tool_grant(expiresAt="2026-09-17T11:30:00Z"),
            tool_grant(revoked=True),
        ):
            with self.subTest(grant=grant):
                self.assertEqual(assess(grants=[grant]).decision, SecurityDecision.BLOCK)

    def test_network_requires_sandbox_and_tool_allowlists(self):
        req = request(requestedNetworkHosts=["api.example.com"])
        result = assess(req=req)
        self.assertEqual(result.decision, SecurityDecision.BLOCK)
        self.assertIn("deny-all", " ".join(result.reasons))

        allowed = assess(
            req=req,
            grants=[tool_grant(networkHosts=["api.example.com"])],
            box=sandbox(networkPolicy="allowlist", networkHosts=["api.example.com"]),
        )
        self.assertEqual(allowed.decision, SecurityDecision.ALLOW)

    def test_credential_is_brokered_and_scoped(self):
        req = request(
            requestedCredentials=[
                {"audience": "api.example.com", "scopes": ["records.read"]}
            ]
        )
        allowed = assess(
            req=req,
            leases=[credential_lease()],
            box=sandbox(secretAccess="brokered"),
        )
        self.assertEqual(allowed.decision, SecurityDecision.ALLOW)

        blocked = assess(req=req, leases=[], box=sandbox(secretAccess="brokered"))
        self.assertEqual(blocked.decision, SecurityDecision.BLOCK)

    def test_raw_secret_value_is_rejected(self):
        lease = credential_lease()
        lease["secretValue"] = "do-not-store-this"
        with self.assertRaisesRegex(SecurityError, "references"):
            validate_credential_lease(lease)

    def test_direct_secret_access_is_prohibited(self):
        result = assess(box=sandbox(secretAccess="direct"))
        self.assertEqual(result.decision, SecurityDecision.BLOCK)

    def test_quarantined_or_prohibited_dependency_blocks(self):
        for status in ("quarantined", "prohibited"):
            with self.subTest(status=status):
                result = assess(deps=[dependency(status=status)])
                self.assertEqual(result.decision, SecurityDecision.BLOCK)

    def test_dependency_below_required_provenance_blocks(self):
        result = assess(
            req=request(minimumProvenance="L2"),
            deps=[dependency(provenanceLevel="L1")],
        )
        self.assertEqual(result.decision, SecurityDecision.BLOCK)

    def test_high_risk_dependency_requires_verified_signature(self):
        result = assess(
            req=request(riskTier="high"),
            deps=[dependency(signatureStatus="missing")],
        )
        self.assertEqual(result.decision, SecurityDecision.BLOCK)
        self.assertIn("signature", " ".join(result.reasons))

    def test_unknown_vulnerability_status_requires_review(self):
        result = assess(deps=[dependency(vulnerabilityStatus="unknown")])
        self.assertEqual(result.decision, SecurityDecision.REVIEW_REQUIRED)

    def test_high_risk_run_requires_telemetry(self):
        result = assess(
            req=request(riskTier="high"), box=sandbox(telemetry=False)
        )
        self.assertEqual(result.decision, SecurityDecision.BLOCK)

    def test_artifact_verification_binds_identity_digest_revision_and_run(self):
        valid, reasons = verify_artifact(
            attestation(),
            expected_artifact_id="ART-1",
            expected_digest="c" * 64,
            expected_revision="rev-1",
            expected_run_id="RUN-1",
            minimum_provenance="L2",
            require_signature=True,
        )
        self.assertTrue(valid)
        self.assertEqual(reasons, ())

        valid, reasons = verify_artifact(
            attestation(artifactDigest="e" * 64, signatureStatus="missing"),
            expected_artifact_id="ART-1",
            expected_digest="c" * 64,
            expected_revision="rev-1",
            expected_run_id="RUN-1",
            minimum_provenance="L2",
            require_signature=True,
        )
        self.assertFalse(valid)
        self.assertIn("artifactDigest does not match", reasons)
        self.assertIn("artifact signature is not verified", reasons)

    def test_containment_plan_revokes_access_and_preserves_evidence(self):
        assessment = assess(
            contents=[content("untrusted", signals=["credential_access"])]
        )
        plan = build_containment_plan(
            assessment,
            incident_id="INC-1",
            project_id="PRJ-1",
            severity="critical",
            generated_at=NOW,
        )
        self.assertIn("revoke-run-credential-leases", plan["actions"])
        self.assertIn("preserve-events-and-telemetry", plan["actions"])
        self.assertIn("pause-affected-project", plan["actions"])
        self.assertEqual(len(plan["planDigest"]), 64)
        validate_containment_plan(plan)

        plan["actions"].append("tampered-action")
        with self.assertRaisesRegex(SecurityError, "digest"):
            validate_containment_plan(plan)

    def test_non_incident_cannot_create_containment_plan(self):
        with self.assertRaisesRegex(SecurityError, "contain decision"):
            build_containment_plan(
                assess(),
                incident_id="INC-1",
                project_id="PRJ-1",
                severity="high",
                generated_at=NOW,
            )

    def test_security_schemas_and_catalog_parse(self):
        root = Path(__file__).parents[1]
        paths = list((root / "schemas").glob("security-*.schema.json"))
        paths.extend(
            [
                root / "schemas/content-descriptor.schema.json",
                root / "schemas/tool-grant.schema.json",
                root / "schemas/credential-lease.schema.json",
                root / "schemas/sandbox-profile.schema.json",
                root / "schemas/dependency-record.schema.json",
                root / "schemas/artifact-attestation.schema.json",
                root / "conformance/security-scenarios.json",
            ]
        )
        self.assertGreaterEqual(len(paths), 9)
        for path in paths:
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
