import {
  evaluateGate,
  type CheckDefinition,
  type CheckResult,
  type EvidenceRecord,
  type GateEvaluation,
  type VerificationEngine,
} from '@v3/verification';

export type ExecutionState =
  | 'planned'
  | 'eligible'
  | 'running'
  | 'verifying'
  | 'reviewing'
  | 'repair_required'
  | 'accepted'
  | 'closed'
  | 'blocked';

export interface ExecutionResult {
  readonly revision: string;
  readonly producerId: string;
  readonly producerIndependenceGroup: string;
  readonly summary: string;
}

export interface ExecutionPort {
  execute(input: {
    readonly projectId: string;
    readonly workPackageId: string;
    readonly objective: string;
    readonly attempt: number;
    readonly kind: 'implementation' | 'repair';
    readonly priorGate?: GateEvaluation;
  }): Promise<ExecutionResult>;
}

export interface ReviewResult {
  readonly approved: boolean;
  readonly summary: string;
  readonly evidence: EvidenceRecord;
}

export interface ReviewPort {
  review(input: {
    readonly projectId: string;
    readonly workPackageId: string;
    readonly objective: string;
    readonly revision: string;
    readonly implementationGroup: string;
    readonly attempt: number;
  }): Promise<ReviewResult>;
}

export interface LifecycleStore {
  transition(workPackageId: string, state: ExecutionState, details?: Readonly<Record<string, unknown>>): Promise<void>;
  recordEvidence(workPackageId: string, evidence: EvidenceRecord): Promise<void>;
  recordGate(workPackageId: string, revision: string, attempt: number, gate: GateEvaluation): Promise<void>;
}

export interface LifecycleOutcome {
  readonly status: 'closed' | 'blocked';
  readonly revision: string;
  readonly attempts: number;
  readonly gate: GateEvaluation;
}

export class ProjectLeadOrchestrator {
  constructor(
    private readonly execution: ExecutionPort,
    private readonly verification: VerificationEngine,
    private readonly review: ReviewPort,
    private readonly store: LifecycleStore,
  ) {}

  async run(input: {
    readonly projectId: string;
    readonly workPackageId: string;
    readonly objective: string;
    readonly repositoryPath: string;
    readonly checks: readonly CheckDefinition[];
    readonly maxRepairAttempts?: number;
  }): Promise<LifecycleOutcome> {
    const maxRepairAttempts = input.maxRepairAttempts ?? 3;
    if (!Number.isInteger(maxRepairAttempts) || maxRepairAttempts < 0) throw new Error('Repair budget must be a non-negative integer');
    await this.store.transition(input.workPackageId, 'eligible');
    let priorGate: GateEvaluation | undefined;
    let latestRevision = '';
    for (let attempt = 0; attempt <= maxRepairAttempts; attempt += 1) {
      await this.store.transition(input.workPackageId, 'running', { attempt, kind: attempt === 0 ? 'implementation' : 'repair' });
      const execution = await this.execution.execute({
        projectId: input.projectId,
        workPackageId: input.workPackageId,
        objective: input.objective,
        attempt,
        kind: attempt === 0 ? 'implementation' : 'repair',
        ...(priorGate === undefined ? {} : { priorGate }),
      });
      latestRevision = execution.revision;
      await this.store.transition(input.workPackageId, 'verifying', { attempt, revision: execution.revision });
      const results: CheckResult[] = [];
      for (const definition of input.checks) {
        const result = await this.verification.run({
          definition,
          cwd: input.repositoryPath,
          subjectId: input.workPackageId,
          subjectRevision: execution.revision,
        });
        results.push(result);
        await this.store.recordEvidence(input.workPackageId, result.evidence);
      }
      await this.store.transition(input.workPackageId, 'reviewing', { attempt, revision: execution.revision });
      const review = await this.review.review({
        projectId: input.projectId,
        workPackageId: input.workPackageId,
        objective: input.objective,
        revision: execution.revision,
        implementationGroup: execution.producerIndependenceGroup,
        attempt,
      });
      await this.store.recordEvidence(input.workPackageId, review.evidence);
      const gate = evaluateGate({
        subjectRevision: execution.revision,
        producerIndependenceGroup: execution.producerIndependenceGroup,
        rules: input.checks.map(({ id }) => ({ checkId: id, required: true, requiresIndependentEvaluator: false })),
        results,
        reviewEvidence: review.evidence,
      });
      await this.store.recordGate(input.workPackageId, execution.revision, attempt, gate);
      if (gate.promotable && review.approved) {
        await this.store.transition(input.workPackageId, 'accepted', { attempt, revision: execution.revision });
        await this.store.transition(input.workPackageId, 'closed', { attempt, revision: execution.revision });
        return { status: 'closed', revision: execution.revision, attempts: attempt + 1, gate };
      }
      priorGate = gate;
      if (attempt < maxRepairAttempts) {
        await this.store.transition(input.workPackageId, 'repair_required', { attempt, reasons: gate.reasons });
      }
    }
    const gate = priorGate ?? { outcome: 'inconclusive', promotable: false, reasons: ['No gate evaluation'], evidenceIds: [] };
    await this.store.transition(input.workPackageId, 'blocked', { repairBudget: maxRepairAttempts, reasons: gate.reasons });
    return { status: 'blocked', revision: latestRevision, attempts: maxRepairAttempts + 1, gate };
  }
}

export class InMemoryLifecycleStore implements LifecycleStore {
  readonly transitions: { workPackageId: string; state: ExecutionState; details?: Readonly<Record<string, unknown>> }[] = [];
  readonly evidence: EvidenceRecord[] = [];
  readonly gates: GateEvaluation[] = [];

  async transition(workPackageId: string, state: ExecutionState, details?: Readonly<Record<string, unknown>>): Promise<void> {
    this.transitions.push({ workPackageId, state, ...(details === undefined ? {} : { details }) });
  }
  async recordEvidence(_workPackageId: string, evidence: EvidenceRecord): Promise<void> { this.evidence.push(evidence); }
  async recordGate(_workPackageId: string, _revision: string, _attempt: number, gate: GateEvaluation): Promise<void> { this.gates.push(gate); }
}
