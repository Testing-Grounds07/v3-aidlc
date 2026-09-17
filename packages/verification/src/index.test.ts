import { describe, expect, it } from 'vitest';

import { VerificationEngine, evaluateGate, type CommandExecutor, type EvidenceRecord } from './index.js';

const executor = (exitCode: number | null, timedOut = false): CommandExecutor => ({
  async run() { return { exitCode, stdout: 'result', stderr: '', timedOut }; },
});

const definition = {
  id: 'CHECK-UNIT' as const,
  title: 'Unit tests',
  kind: 'test_result' as const,
  command: ['pnpm', 'test'] as const,
  timeoutMs: 10_000,
};

async function result(exitCode = 0) {
  return new VerificationEngine(executor(exitCode)).run({
    definition, cwd: '/repo', subjectId: 'WP-1', subjectRevision: 'rev-1', now: new Date('2026-09-17T00:00:00Z'),
  });
}

const review = (group = 'review-team', revision = 'rev-1', assertion = 'approved'): EvidenceRecord => ({
  id: 'EVID-REVIEW-1', kind: 'review_disposition', subjectId: 'WP-1', subjectRevision: revision,
  producerId: 'reviewer-1', producerRole: 'reviewer', producerIndependenceGroup: group,
  collectedAt: new Date('2026-09-17T00:00:01Z'), locator: 'review://1', sha256: 'a'.repeat(64), assertions: [assertion],
});

describe('VerificationEngine', () => {
  it('records digest-bound passing evidence', async () => {
    await expect(result()).resolves.toMatchObject({ status: 'passed', evidence: { subjectRevision: 'rev-1', kind: 'test_result' } });
  });

  it('distinguishes a failed check from an execution error', async () => {
    await expect(result(1)).resolves.toMatchObject({ status: 'failed' });
    await expect(new VerificationEngine(executor(null, true)).run({
      definition, cwd: '/repo', subjectId: 'WP-1', subjectRevision: 'rev-1',
    })).resolves.toMatchObject({ status: 'error' });
  });
});

describe('evaluateGate', () => {
  it('passes only matching evidence and an independent approval', async () => {
    expect(evaluateGate({
      subjectRevision: 'rev-1', producerIndependenceGroup: 'implementation-team',
      rules: [{ checkId: 'CHECK-UNIT', required: true, requiresIndependentEvaluator: false }],
      results: [await result()], reviewEvidence: review(),
    })).toMatchObject({ outcome: 'passed', promotable: true });
  });

  it('is inconclusive for stale evidence or a non-independent reviewer', async () => {
    expect(evaluateGate({
      subjectRevision: 'rev-2', producerIndependenceGroup: 'same-team',
      rules: [{ checkId: 'CHECK-UNIT', required: true, requiresIndependentEvaluator: false }],
      results: [await result()], reviewEvidence: review('same-team', 'rev-2'),
    })).toMatchObject({ outcome: 'inconclusive', promotable: false });
  });
});
