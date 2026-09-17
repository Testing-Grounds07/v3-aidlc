export interface WorkObservation {
  readonly workPackageId: string;
  readonly route: string;
  readonly mode: string;
  readonly posture: string;
  readonly startedAt: Date;
  readonly closedAt?: Date;
  readonly repairAttempts: number;
  readonly verificationAttempts: number;
  readonly decisionWaitMs: number;
  readonly blockedMs: number;
  readonly accepted: boolean;
}

export interface HealthMetric {
  readonly value: number | null;
  readonly unit: 'ratio' | 'milliseconds' | 'count';
  readonly sampleSize: number;
  readonly status: 'healthy' | 'watch' | 'unhealthy' | 'inconclusive';
  readonly explanation: string;
}

export interface ProcessHealthReport {
  readonly projectId: string;
  readonly windowStart: Date;
  readonly windowEnd: Date;
  readonly dimensions: Readonly<{ route?: string; mode?: string; posture?: string }>;
  readonly metrics: Readonly<{
    firstPassYield: HealthMetric;
    medianCycleTime: HealthMetric;
    repairRate: HealthMetric;
    medianDecisionWait: HealthMetric;
    blockedShare: HealthMetric;
  }>;
  readonly recommendations: readonly string[];
}

const median = (values: readonly number[]): number => {
  const ordered = [...values].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 === 0 ? ((ordered[middle - 1] ?? 0) + (ordered[middle] ?? 0)) / 2 : ordered[middle] ?? 0;
};

function metric(value: number | null, unit: HealthMetric['unit'], sampleSize: number, thresholds: readonly [number, number], higherIsBetter: boolean, explanation: string): HealthMetric {
  if (value === null || sampleSize < 3) return { value, unit, sampleSize, status: 'inconclusive', explanation: `Not enough comparable work yet. ${explanation}` };
  const [healthy, unhealthy] = thresholds;
  const status = higherIsBetter
    ? value >= healthy ? 'healthy' : value < unhealthy ? 'unhealthy' : 'watch'
    : value <= healthy ? 'healthy' : value > unhealthy ? 'unhealthy' : 'watch';
  return { value, unit, sampleSize, status, explanation };
}

export function analyzeProcessHealth(input: {
  readonly projectId: string;
  readonly observations: readonly WorkObservation[];
  readonly windowStart: Date;
  readonly windowEnd: Date;
  readonly dimensions?: Readonly<{ route?: string; mode?: string; posture?: string }>;
}): ProcessHealthReport {
  if (input.windowEnd <= input.windowStart) throw new Error('Health window must end after it starts');
  const dimensions = input.dimensions ?? {};
  const sample = input.observations.filter((item) =>
    item.startedAt >= input.windowStart && item.startedAt < input.windowEnd
    && (dimensions.route === undefined || item.route === dimensions.route)
    && (dimensions.mode === undefined || item.mode === dimensions.mode)
    && (dimensions.posture === undefined || item.posture === dimensions.posture));
  const completed = sample.filter((item): item is WorkObservation & { closedAt: Date } => item.closedAt !== undefined);
  const accepted = completed.filter(({ accepted }) => accepted);
  const firstPass = accepted.filter(({ repairAttempts }) => repairAttempts === 0).length;
  const totalDuration = completed.reduce((sum, item) => sum + (item.closedAt.getTime() - item.startedAt.getTime()), 0);
  const totalBlocked = completed.reduce((sum, item) => sum + item.blockedMs, 0);
  const firstPassYield = metric(accepted.length === 0 ? null : firstPass / accepted.length, 'ratio', accepted.length, [0.8, 0.5], true, 'Shows how often work passes without repair.');
  const medianCycleTime = metric(completed.length === 0 ? null : median(completed.map((item) => item.closedAt.getTime() - item.startedAt.getTime())), 'milliseconds', completed.length, [86_400_000, 604_800_000], false, 'Measures elapsed time from start to accepted closure.');
  const repairRate = metric(accepted.length === 0 ? null : accepted.reduce((sum, item) => sum + item.repairAttempts, 0) / accepted.length, 'count', accepted.length, [0.5, 2], false, 'Counts repair loops per accepted item.');
  const decisionSample = completed.filter(({ decisionWaitMs }) => decisionWaitMs > 0);
  const medianDecisionWait = metric(decisionSample.length === 0 ? 0 : median(decisionSample.map(({ decisionWaitMs }) => decisionWaitMs)), 'milliseconds', completed.length, [3_600_000, 86_400_000], false, 'Measures time spent waiting for human choices.');
  const blockedShare = metric(totalDuration === 0 ? null : totalBlocked / totalDuration, 'ratio', completed.length, [0.1, 0.35], false, 'Shows how much elapsed delivery time was blocked.');
  const metrics = { firstPassYield, medianCycleTime, repairRate, medianDecisionWait, blockedShare };
  const recommendations: string[] = [];
  if (repairRate.status === 'unhealthy') recommendations.push('Review recurring findings before increasing parallel work.');
  if (medianDecisionWait.status === 'unhealthy') recommendations.push('Move predictable choices earlier or create a bounded standing delegation.');
  if (blockedShare.status === 'unhealthy') recommendations.push('Inspect the most common dependency and environment blockers.');
  if (Object.values(metrics).every(({ status }) => status === 'inconclusive')) recommendations.push('Collect at least three comparable completed items before changing the process.');
  return { projectId: input.projectId, windowStart: input.windowStart, windowEnd: input.windowEnd, dimensions, metrics, recommendations };
}

export interface ProcessHealthService { getLatest(projectId: string): Promise<ProcessHealthReport | null> }
export class InMemoryProcessHealthService implements ProcessHealthService {
  constructor(private readonly reports: readonly ProcessHealthReport[] = []) {}
  async getLatest(projectId: string): Promise<ProcessHealthReport | null> { return [...this.reports].reverse().find((report) => report.projectId === projectId) ?? null; }
}
