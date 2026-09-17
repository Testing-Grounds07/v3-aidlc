import json
import unittest
from pathlib import Path

from v3_aidlc.operations import (
    BudgetDecision,
    OperationsError,
    ReadinessOutcome,
    aggregate_usage,
    assess_restore,
    evaluate_budget,
    evaluate_readiness,
    evaluate_slo,
    validate_migration,
    validate_telemetry,
    validate_topology,
)


def telemetry(**overrides):
    value = {"recordId":"REC-1","traceId":"TRACE-1","spanId":"SPAN-1","projectId":"PRJ-1","signalKind":"trace","name":"run.dispatch","timestamp":"2026-09-17T12:00:00Z","sensitivity":"internal","redacted":True,"attributes":{"run.id":"RUN-1","status":"ok"}}
    value.update(overrides)
    return value


def usage(entry_id="USE-1", **overrides):
    value = {"entryId":entry_id,"projectId":"PRJ-1","workPackageId":"WP-1","runId":"RUN-1","provider":"provider","model":"model","occurredAt":"2026-09-17T12:00:00Z","currency":"USD","inputUnits":100,"outputUnits":20,"toolSeconds":3,"storageByteHours":4,"costMicros":5000}
    value.update(overrides)
    return value


class OperationsTest(unittest.TestCase):
    def test_redacted_correlated_telemetry_is_valid(self):
        validate_telemetry(telemetry())

    def test_telemetry_rejects_prompt_and_secret_fields(self):
        for key in ("prompt.text", "credential.token", "response.content"):
            with self.subTest(key=key), self.assertRaisesRegex(OperationsError, "prohibited"):
                validate_telemetry(telemetry(attributes={key:"sensitive"}))

    def test_ratio_slo_tracks_error_budget(self):
        slo={"sloId":"SLO-1","service":"project-lead","sliKind":"availability","window":"30d","target":0.99,"minimumSamples":3}
        result=evaluate_slo(slo,[1.0,1.0,0.98])
        self.assertTrue(result.met)
        self.assertGreaterEqual(result.error_budget_remaining,0)

    def test_latency_slo_uses_declared_percentile(self):
        slo={"sloId":"SLO-2","service":"gateway","sliKind":"latency_ms","window":"1h","target":200,"minimumSamples":4,"percentile":0.75}
        self.assertTrue(evaluate_slo(slo,[50,100,150,500]).met)

    def test_insufficient_slo_samples_are_inconclusive(self):
        slo={"sloId":"SLO-1","service":"lead","sliKind":"success_ratio","window":"1h","target":0.9,"minimumSamples":3}
        with self.assertRaisesRegex(OperationsError,"insufficient"):
            evaluate_slo(slo,[1.0])

    def test_usage_aggregates_without_rounding_currency(self):
        result=aggregate_usage([usage(),usage("USE-2",costMicros=7000,inputUnits=50)])
        self.assertEqual(result["costMicros"],12000)
        self.assertEqual(result["inputUnits"],150)

    def test_duplicate_usage_is_rejected(self):
        with self.assertRaisesRegex(OperationsError,"duplicate"):
            aggregate_usage([usage(),usage()])

    def test_budget_warns_then_blocks(self):
        budget={"budgetId":"BUD-1","dimension":"costMicros","period":"monthly","limit":100,"warnAt":80}
        self.assertEqual(evaluate_budget(budget,80).decision,BudgetDecision.WARN)
        result=evaluate_budget(budget,101)
        self.assertEqual(result.decision,BudgetDecision.BLOCK)
        self.assertEqual(result.remaining,-1)

    def test_restore_must_meet_rpo_rto_and_integrity(self):
        policy={"policyId":"BACKUP-1","dataSet":"state","rpoSeconds":3600,"rtoSeconds":600}
        observation={"backupId":"B-1","createdAt":"2026-09-17T11:30:00Z","restoreDurationSeconds":300,"encrypted":True,"integrityVerified":True,"restoreTestPassed":True}
        self.assertTrue(assess_restore(policy,observation,now="2026-09-17T12:00:00Z")[0])
        observation["integrityVerified"]=False
        self.assertFalse(assess_restore(policy,observation,now="2026-09-17T12:00:00Z")[0])

    def test_migration_requires_contiguous_evidenced_phases(self):
        migration={"migrationId":"MIG-1","fromVersion":"1","toVersion":"2","currentPhase":"verify","completedPhases":["expand","backfill"],"phaseEvidence":{"expand":["E1"],"backfill":["E2"]},"backwardCompatible":True,"rollbackProcedure":"Restore version 1."}
        validate_migration(migration)
        migration["completedPhases"]=["backfill"]
        with self.assertRaisesRegex(OperationsError,"contiguous"):
            validate_migration(migration)

    def test_pre_switch_migration_must_remain_compatible(self):
        migration={"migrationId":"MIG-1","fromVersion":"1","toVersion":"2","currentPhase":"backfill","completedPhases":["expand"],"phaseEvidence":{"expand":["E1"]},"backwardCompatible":False,"rollbackProcedure":"Rollback."}
        with self.assertRaisesRegex(OperationsError,"backward compatible"):
            validate_migration(migration)

    def test_topology_requires_one_state_authority_and_encrypted_links(self):
        topology={"topologyId":"TOP-1","environment":"production","components":[{"id":"api","role":"gateway","trustZone":"edge","dataClassification":"internal","replicas":2,"stateAuthority":False},{"id":"db","role":"state","trustZone":"data","dataClassification":"restricted","replicas":1,"stateAuthority":True}],"connections":[{"source":"api","target":"db","encrypted":True}]}
        validate_topology(topology)
        topology["connections"][0]["encrypted"]=False
        with self.assertRaisesRegex(OperationsError,"encrypted"):
            validate_topology(topology)

    def test_readiness_requires_all_mandatory_evidence(self):
        checklist={"checklistId":"READY-1","controls":[{"id":"slo","required":True},{"id":"restore","required":True}]}
        evidence=[{"controlId":"slo","status":"passed","evidenceIds":["E1"]},{"controlId":"restore","status":"passed","evidenceIds":["E2"]}]
        self.assertEqual(evaluate_readiness(checklist,evidence).outcome,ReadinessOutcome.READY)
        self.assertEqual(evaluate_readiness(checklist,evidence[:1]).outcome,ReadinessOutcome.INCONCLUSIVE)

    def test_failed_required_control_is_not_ready(self):
        checklist={"checklistId":"READY-1","controls":[{"id":"restore","required":True}]}
        evidence=[{"controlId":"restore","status":"failed","evidenceIds":["E1"]}]
        self.assertEqual(evaluate_readiness(checklist,evidence).outcome,ReadinessOutcome.NOT_READY)

    def test_operations_schemas_parse(self):
        root=Path(__file__).parents[1]
        paths=list((root/"schemas").glob("operations-*.schema.json"))+[root/"conformance/operations-scenarios.json"]
        self.assertGreaterEqual(len(paths),7)
        for path in paths:
            json.loads(path.read_text())


if __name__ == "__main__": unittest.main()
