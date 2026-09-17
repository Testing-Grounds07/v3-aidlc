import { createHash } from 'node:crypto';

export interface EvaluationCase {
  readonly id: string;
  readonly version: string;
  readonly taskKind: string;
  readonly contextRevision: string;
  readonly expectedAssertions: readonly string[];
  readonly hardRequirements: readonly string[];
}

export interface RubricDimension {
  readonly id: string;
  readonly weight: number;
  readonly minimumScore: number;
}

export interface CandidateResult {
  readonly id: string;
  readonly caseId: string;
  readonly caseVersion: string;
  readonly contextRevision: string;
  readonly profileId: string;
  readonly providerResultRef: string;
  readonly assertions: readonly string[];
  readonly evidenceIds: readonly string[];
  readonly latencyMs: number;
  readonly costMicros: number;
}

export interface DimensionScore {
  readonly dimensionId: string;
  readonly score: number;
  readonly explanation: string;
  readonly evidenceIds: readonly string[];
}

export interface EvaluationResult {
  readonly candidateId: string;
  readonly caseId: string;
  readonly evaluatorId: string;
  readonly evaluatorIndependenceGroup: string;
  readonly scores: readonly DimensionScore[];
  readonly weightedScore: number;
  readonly passed: boolean;
  readonly failures: readonly string[];
  readonly digest: string;
}

export interface EvaluationScorer {
  readonly id: string;
  readonly independenceGroup: string;
  score(input: { readonly testCase: EvaluationCase; readonly candidate: CandidateResult; readonly rubric: readonly RubricDimension[] }): Promise<readonly DimensionScore[]>;
}

export class EvaluationError extends Error {}

export async function evaluateCandidate(input: {
  readonly testCase: EvaluationCase;
  readonly candidate: CandidateResult;
  readonly rubric: readonly RubricDimension[];
  readonly scorer: EvaluationScorer;
  readonly candidateIndependenceGroup: string;
}): Promise<EvaluationResult> {
  if (input.candidate.caseId !== input.testCase.id || input.candidate.caseVersion !== input.testCase.version) throw new EvaluationError('Candidate is bound to a different evaluation case');
  if (input.candidate.contextRevision !== input.testCase.contextRevision) throw new EvaluationError('Candidate used a different context revision');
  if (input.candidate.evidenceIds.length === 0) throw new EvaluationError('Candidate has no evaluation evidence');
  if (input.scorer.independenceGroup === input.candidateIndependenceGroup) throw new EvaluationError('Evaluator must be independent from the candidate producer');
  if (input.rubric.length === 0 || input.rubric.some(({ weight, minimumScore }) => weight <= 0 || minimumScore < 0 || minimumScore > 1)) throw new EvaluationError('Rubric contains invalid weights or thresholds');
  const scores = await input.scorer.score({ testCase: input.testCase, candidate: input.candidate, rubric: input.rubric });
  if (scores.length !== input.rubric.length) throw new EvaluationError('Evaluator returned an incomplete rubric');
  const failures: string[] = [];
  let weighted = 0;
  let weights = 0;
  for (const dimension of input.rubric) {
    const score = scores.find(({ dimensionId }) => dimensionId === dimension.id);
    if (score === undefined || score.score < 0 || score.score > 1 || score.evidenceIds.length === 0) throw new EvaluationError(`Invalid score for ${dimension.id}`);
    if (score.score < dimension.minimumScore) failures.push(`${dimension.id} is below its minimum`);
    weighted += score.score * dimension.weight;
    weights += dimension.weight;
  }
  for (const requirement of input.testCase.hardRequirements) if (!input.candidate.assertions.includes(requirement)) failures.push(`Missing hard requirement: ${requirement}`);
  const weightedScore = weighted / weights;
  const canonical = JSON.stringify({ candidateId: input.candidate.id, caseId: input.testCase.id, evaluatorId: input.scorer.id, scores, weightedScore, failures });
  return {
    candidateId: input.candidate.id, caseId: input.testCase.id, evaluatorId: input.scorer.id,
    evaluatorIndependenceGroup: input.scorer.independenceGroup, scores, weightedScore,
    passed: failures.length === 0, failures,
    digest: createHash('sha256').update(canonical).digest('hex'),
  };
}

export interface ProviderBenchmark {
  readonly profileId: string;
  readonly taskKind: string;
  readonly sampleSize: number;
  readonly passRate: number;
  readonly meanScore: number;
  readonly medianLatencyMs: number;
  readonly meanCostMicros: number;
  readonly measuredAt: Date;
}

export function selectProfile(input: {
  readonly eligibleProfileIds: readonly string[];
  readonly taskKind: string;
  readonly posture: 'fast' | 'balanced' | 'assured';
  readonly benchmarks: readonly ProviderBenchmark[];
  readonly minimumSamples?: number;
}): { readonly profileId: string; readonly reason: string } | null {
  const minimumSamples = input.minimumSamples ?? 5;
  const eligible = input.benchmarks.filter((item) => input.eligibleProfileIds.includes(item.profileId) && item.taskKind === input.taskKind && item.sampleSize >= minimumSamples);
  if (eligible.length === 0) return null;
  eligible.sort((left, right) => {
    if (input.posture === 'fast') return left.medianLatencyMs - right.medianLatencyMs || right.passRate - left.passRate || left.profileId.localeCompare(right.profileId);
    if (input.posture === 'assured') return right.passRate - left.passRate || right.meanScore - left.meanScore || left.profileId.localeCompare(right.profileId);
    const leftValue = left.meanScore * left.passRate / Math.max(1, left.meanCostMicros);
    const rightValue = right.meanScore * right.passRate / Math.max(1, right.meanCostMicros);
    return rightValue - leftValue || left.profileId.localeCompare(right.profileId);
  });
  const selected = eligible[0];
  if (selected === undefined) return null;
  return { profileId: selected.profileId, reason: `${input.posture} routing used ${selected.sampleSize} comparable evaluation samples.` };
}

export function detectRegression(current: ProviderBenchmark, baseline: ProviderBenchmark, tolerance = 0.05): readonly string[] {
  if (current.profileId !== baseline.profileId || current.taskKind !== baseline.taskKind) throw new EvaluationError('Regression comparison requires the same profile and task kind');
  const findings: string[] = [];
  if (current.passRate < baseline.passRate - tolerance) findings.push('pass rate regressed');
  if (current.meanScore < baseline.meanScore - tolerance) findings.push('quality score regressed');
  if (current.medianLatencyMs > baseline.medianLatencyMs * (1 + tolerance)) findings.push('latency regressed');
  return findings;
}
