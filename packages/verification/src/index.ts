import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';

export type EvidenceKind =
  | 'artifact'
  | 'test_result'
  | 'build_result'
  | 'review_disposition'
  | 'scan_result'
  | 'observation'
  | 'metric'
  | 'decision'
  | 'provenance_manifest';

export interface EvidenceRecord {
  readonly id: string;
  readonly kind: EvidenceKind;
  readonly subjectId: string;
  readonly subjectRevision: string;
  readonly producerId: string;
  readonly producerRole: string;
  readonly producerIndependenceGroup: string;
  readonly collectedAt: Date;
  readonly locator: string;
  readonly sha256: string;
  readonly assertions: readonly string[];
}

export interface CheckDefinition {
  readonly id: `CHECK-${string}`;
  readonly title: string;
  readonly kind: Extract<EvidenceKind, 'test_result' | 'build_result' | 'scan_result'>;
  readonly command: readonly [string, ...string[]];
  readonly timeoutMs: number;
}

export interface CommandResult {
  readonly exitCode: number | null;
  readonly stdout: string;
  readonly stderr: string;
  readonly timedOut: boolean;
}

export interface CommandExecutor {
  run(command: readonly [string, ...string[]], cwd: string, timeoutMs: number): Promise<CommandResult>;
}

export class ExecFileCommandExecutor implements CommandExecutor {
  async run(command: readonly [string, ...string[]], cwd: string, timeoutMs: number): Promise<CommandResult> {
    return new Promise((resolve) => {
      const [file, ...args] = command;
      execFile(file, args, { cwd, timeout: timeoutMs, maxBuffer: 10 * 1024 * 1024 }, (error, stdout, stderr) => {
        const failure = error as NodeJS.ErrnoException & { code?: string | number; killed?: boolean } | null;
        resolve({
          exitCode: failure === null ? 0 : typeof failure.code === 'number' ? failure.code : null,
          stdout,
          stderr,
          timedOut: failure?.killed === true || failure?.code === 'ETIMEDOUT',
        });
      });
    });
  }
}

export interface CheckResult {
  readonly checkId: string;
  readonly status: 'passed' | 'failed' | 'error';
  readonly evidence: EvidenceRecord;
}

const digest = (value: string): string => createHash('sha256').update(value).digest('hex');

export class VerificationEngine {
  constructor(private readonly executor: CommandExecutor = new ExecFileCommandExecutor()) {}

  async run(input: {
    readonly definition: CheckDefinition;
    readonly cwd: string;
    readonly subjectId: string;
    readonly subjectRevision: string;
    readonly producerId?: string;
    readonly now?: Date;
  }): Promise<CheckResult> {
    const result = await this.executor.run(input.definition.command, input.cwd, input.definition.timeoutMs);
    const status = result.timedOut || result.exitCode === null ? 'error' : result.exitCode === 0 ? 'passed' : 'failed';
    const body = JSON.stringify({
      command: input.definition.command,
      exitCode: result.exitCode,
      stdout: result.stdout,
      stderr: result.stderr,
      timedOut: result.timedOut,
    });
    const sha256 = digest(body);
    return {
      checkId: input.definition.id,
      status,
      evidence: {
        id: `EVID-${input.definition.id.slice(6)}-${sha256.slice(0, 12).toUpperCase()}`,
        kind: input.definition.kind,
        subjectId: input.subjectId,
        subjectRevision: input.subjectRevision,
        producerId: input.producerId ?? 'v3-verification-engine',
        producerRole: 'verifier',
        producerIndependenceGroup: 'deterministic-runtime',
        collectedAt: input.now ?? new Date(),
        locator: `sha256:${sha256}`,
        sha256,
        assertions: [`${input.definition.title}: ${status}`],
      },
    };
  }
}

export interface GateRule {
  readonly checkId: string;
  readonly required: boolean;
  readonly requiresIndependentEvaluator: boolean;
}

export interface GateEvaluation {
  readonly outcome: 'passed' | 'failed' | 'inconclusive';
  readonly promotable: boolean;
  readonly reasons: readonly string[];
  readonly evidenceIds: readonly string[];
}

export function evaluateGate(input: {
  readonly subjectRevision: string;
  readonly producerIndependenceGroup: string;
  readonly rules: readonly GateRule[];
  readonly results: readonly CheckResult[];
  readonly reviewEvidence?: EvidenceRecord;
}): GateEvaluation {
  const reasons: string[] = [];
  const evidenceIds: string[] = [];
  let failed = false;
  for (const rule of input.rules) {
    const result = input.results.find(({ checkId }) => checkId === rule.checkId);
    if (result === undefined) {
      if (rule.required) reasons.push(`${rule.checkId} has no result`);
      continue;
    }
    evidenceIds.push(result.evidence.id);
    if (result.evidence.subjectRevision !== input.subjectRevision) reasons.push(`${rule.checkId} evidence is stale`);
    if (result.status === 'failed') failed = true;
    if (result.status === 'error') reasons.push(`${rule.checkId} could not be evaluated`);
  }
  const review = input.reviewEvidence;
  if (review === undefined) reasons.push('independent review evidence is missing');
  else {
    evidenceIds.push(review.id);
    if (review.subjectRevision !== input.subjectRevision) reasons.push('review evidence is stale');
    if (review.producerIndependenceGroup === input.producerIndependenceGroup) reasons.push('reviewer is not independent');
    if (!review.assertions.includes('approved')) failed = true;
  }
  if (failed) return { outcome: 'failed', promotable: false, reasons, evidenceIds };
  if (reasons.length > 0) return { outcome: 'inconclusive', promotable: false, reasons, evidenceIds };
  return { outcome: 'passed', promotable: true, reasons: [], evidenceIds };
}
