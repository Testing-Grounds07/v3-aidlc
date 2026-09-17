import { describe, expect, it } from 'vitest';
import { InMemoryLifecycleStore, ProjectLeadOrchestrator, type ExecutionPort, type ReviewPort } from './index.js';
import { VerificationEngine, type CommandExecutor, type EvidenceRecord } from '@v3/verification';

const check = { id: 'CHECK-UNIT' as const, title: 'Unit tests', kind: 'test_result' as const, command: ['pnpm', 'test'] as const, timeoutMs: 1000 };

function reviewEvidence(revision: string, approved: boolean): EvidenceRecord {
  return {
    id: `EVID-REVIEW-${revision}`, kind: 'review_disposition', subjectId: 'WP-1', subjectRevision: revision,
    producerId: 'reviewer', producerRole: 'reviewer', producerIndependenceGroup: 'review-team',
    collectedAt: new Date(), locator: `review://${revision}`, sha256: 'a'.repeat(64),
    assertions: [approved ? 'approved' : 'changes_requested'],
  };
}

describe('ProjectLeadOrchestrator', () => {
  it('repairs a failed attempt, repeats verification and review, then closes', async () => {
    let checkAttempt = 0;
    const executor: CommandExecutor = { async run() { checkAttempt += 1; return { exitCode: checkAttempt === 1 ? 1 : 0, stdout: '', stderr: '', timedOut: false }; } };
    const execution: ExecutionPort = { async execute({ attempt }) { return { revision: `rev-${attempt}`, producerId: 'builder', producerIndependenceGroup: 'build-team', summary: 'done' }; } };
    const review: ReviewPort = { async review({ revision, attempt }) { return { approved: attempt > 0, summary: 'reviewed', evidence: reviewEvidence(revision, attempt > 0) }; } };
    const store = new InMemoryLifecycleStore();
    const outcome = await new ProjectLeadOrchestrator(execution, new VerificationEngine(executor), review, store).run({
      projectId: 'PRJ-1', workPackageId: 'WP-1', objective: 'Change it', repositoryPath: '/repo', checks: [check],
    });
    expect(outcome).toMatchObject({ status: 'closed', revision: 'rev-1', attempts: 2, gate: { outcome: 'passed' } });
    expect(store.transitions.map(({ state }) => state)).toEqual([
      'eligible', 'running', 'verifying', 'reviewing', 'repair_required', 'running', 'verifying', 'reviewing', 'accepted', 'closed',
    ]);
    expect(store.evidence).toHaveLength(4);
  });

  it('blocks after the bounded repair budget is exhausted', async () => {
    const executor: CommandExecutor = { async run() { return { exitCode: 1, stdout: '', stderr: 'broken', timedOut: false }; } };
    const execution: ExecutionPort = { async execute({ attempt }) { return { revision: `rev-${attempt}`, producerId: 'builder', producerIndependenceGroup: 'build-team', summary: 'done' }; } };
    const review: ReviewPort = { async review({ revision }) { return { approved: false, summary: 'changes requested', evidence: reviewEvidence(revision, false) }; } };
    const store = new InMemoryLifecycleStore();
    const outcome = await new ProjectLeadOrchestrator(execution, new VerificationEngine(executor), review, store).run({
      projectId: 'PRJ-1', workPackageId: 'WP-1', objective: 'Change it', repositoryPath: '/repo', checks: [check], maxRepairAttempts: 1,
    });
    expect(outcome).toMatchObject({ status: 'blocked', attempts: 2 });
    expect(store.transitions.at(-1)?.state).toBe('blocked');
  });
});
