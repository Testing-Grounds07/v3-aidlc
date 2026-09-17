import { describe, expect, it } from 'vitest';
import { EvaluationError, detectRegression, evaluateCandidate, selectProfile, type EvaluationScorer, type ProviderBenchmark } from './index.js';

const testCase = { id: 'CASE-1', version: '1.0.0', taskKind: 'code-change', contextRevision: 'ctx-1', expectedAssertions: ['tests'], hardRequirements: ['tests-pass'] };
const candidate = { id: 'CAND-1', caseId: 'CASE-1', caseVersion: '1.0.0', contextRevision: 'ctx-1', profileId: 'PROFILE-A', providerResultRef: 'result://1', assertions: ['tests-pass'], evidenceIds: ['EVID-1'], latencyMs: 100, costMicros: 20 };
const rubric = [{ id: 'correctness', weight: 2, minimumScore: 0.8 }, { id: 'clarity', weight: 1, minimumScore: 0.6 }];
const scorer: EvaluationScorer = { id: 'SCORER-1', independenceGroup: 'eval-team', async score() { return [{ dimensionId: 'correctness', score: 0.9, explanation: 'Passes checks', evidenceIds: ['EVID-1'] }, { dimensionId: 'clarity', score: 0.7, explanation: 'Clear', evidenceIds: ['EVID-1'] }]; } };

describe('provider evaluations', () => {
  it('produces a digest-bound independent rubric result', async () => {
    await expect(evaluateCandidate({ testCase, candidate, rubric, scorer, candidateIndependenceGroup: 'provider-team' })).resolves.toMatchObject({ passed: true, weightedScore: 0.8333333333333334 });
  });
  it('rejects self-evaluation and context drift', async () => {
    await expect(evaluateCandidate({ testCase, candidate, rubric, scorer, candidateIndependenceGroup: 'eval-team' })).rejects.toThrow(EvaluationError);
    await expect(evaluateCandidate({ testCase, candidate: { ...candidate, contextRevision: 'other' }, rubric, scorer, candidateIndependenceGroup: 'provider-team' })).rejects.toThrow('different context');
  });
});

const benchmark = (profileId: string, passRate: number, score: number, latency: number, cost: number): ProviderBenchmark => ({ profileId, taskKind: 'code-change', sampleSize: 10, passRate, meanScore: score, medianLatencyMs: latency, meanCostMicros: cost, measuredAt: new Date() });

describe('evidence-based routing', () => {
  it('changes the ranking by posture and remains deterministic', () => {
    const benchmarks = [benchmark('fast', 0.8, 0.8, 100, 10), benchmark('assured', 0.98, 0.95, 500, 40)];
    expect(selectProfile({ eligibleProfileIds: ['fast', 'assured'], taskKind: 'code-change', posture: 'fast', benchmarks })?.profileId).toBe('fast');
    expect(selectProfile({ eligibleProfileIds: ['fast', 'assured'], taskKind: 'code-change', posture: 'assured', benchmarks })?.profileId).toBe('assured');
  });
  it('will not route from insufficient samples', () => {
    expect(selectProfile({ eligibleProfileIds: ['fast'], taskKind: 'code-change', posture: 'balanced', benchmarks: [{ ...benchmark('fast', .9, .9, 100, 10), sampleSize: 2 }] })).toBeNull();
  });
  it('detects quality and latency regressions on comparable benchmarks', () => {
    expect(detectRegression(benchmark('p', .8, .8, 120, 10), benchmark('p', .95, .95, 100, 10))).toEqual(['pass rate regressed', 'quality score regressed', 'latency regressed']);
  });
});
