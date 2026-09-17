export type Identifier = string;

export interface EntityReference {
  readonly id: Identifier;
  readonly version: number;
}

export type DeliveryPosture =
  | 'explore'
  | 'fast'
  | 'balanced'
  | 'assured'
  | 'emergency';

export type LifecycleStage =
  | 'discovery'
  | 'definition'
  | 'design'
  | 'implementation'
  | 'validation'
  | 'release'
  | 'operation'
  | 'retirement';

export type ProjectStatus = 'active' | 'paused' | 'completed' | 'cancelled';
export type RequirementStatus = 'draft' | 'approved' | 'superseded';
export type PlanStatus = 'draft' | 'approved' | 'superseded';

export type WorkPackageStatus =
  | 'proposed'
  | 'planned'
  | 'eligible'
  | 'leased'
  | 'running'
  | 'evidence_pending'
  | 'verifying'
  | 'reviewing'
  | 'repair_required'
  | 'replan_required'
  | 'decision_required'
  | 'blocked'
  | 'accepted'
  | 'closed'
  | 'cancelled'
  | 'superseded';

export interface Project {
  readonly id: Identifier;
  readonly name: string;
  readonly description: string;
  readonly status: ProjectStatus;
  readonly version: number;
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

export interface Requirement {
  readonly id: Identifier;
  readonly projectId: Identifier;
  readonly title: string;
  readonly description: string;
  readonly status: RequirementStatus;
  readonly version: number;
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

export interface AcceptanceCriterion {
  readonly id: Identifier;
  readonly requirementId: Identifier;
  readonly statement: string;
  readonly verificationMethod: string;
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

export interface Plan {
  readonly id: Identifier;
  readonly projectId: Identifier;
  readonly title: string;
  readonly objective: string;
  readonly status: PlanStatus;
  readonly version: number;
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

export interface WorkPackage {
  readonly id: Identifier;
  readonly projectId: Identifier;
  readonly planId: Identifier;
  readonly title: string;
  readonly objective: string;
  readonly status: WorkPackageStatus;
  readonly version: number;
  readonly intentIds: readonly Identifier[];
  readonly routeInstanceId?: Identifier;
  readonly workstreamId?: Identifier;
  readonly unitId?: Identifier;
  readonly boltId?: Identifier;
  readonly stage: LifecycleStage;
  readonly modeId?: Identifier;
  readonly posture: DeliveryPosture;
  readonly riskProfileId?: Identifier;
  readonly expectedOutcomeTypes: readonly string[];
  readonly promotionTarget?: string;
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

export interface LifecycleEvent<TPayload extends Record<string, unknown> = Record<string, unknown>> {
  readonly id: Identifier;
  readonly projectId: Identifier;
  readonly type: string;
  readonly aggregateType: string;
  readonly aggregateId: Identifier;
  readonly aggregateVersion: number;
  readonly payload: Readonly<TPayload>;
  readonly occurredAt: Date;
}

export interface ProjectGraph {
  readonly project: Project;
  readonly requirements: readonly (Requirement & {
    readonly acceptanceCriteria: readonly AcceptanceCriterion[];
  })[];
  readonly plans: readonly (Plan & { readonly workPackages: readonly WorkPackage[] })[];
  readonly events: readonly LifecycleEvent[];
}

export class DomainValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DomainValidationError';
  }
}

export class InvalidTransitionError extends DomainValidationError {
  constructor(from: WorkPackageStatus, to: WorkPackageStatus) {
    super(`Work package cannot transition from ${from} to ${to}`);
    this.name = 'InvalidTransitionError';
  }
}

const WORK_PACKAGE_TRANSITIONS: Readonly<Record<WorkPackageStatus, readonly WorkPackageStatus[]>> = {
  proposed: ['planned', 'cancelled', 'superseded'],
  planned: ['eligible', 'blocked', 'cancelled', 'superseded'],
  eligible: ['leased', 'blocked', 'cancelled', 'superseded'],
  leased: ['running', 'eligible', 'blocked', 'cancelled'],
  running: ['evidence_pending', 'verifying', 'repair_required', 'replan_required', 'decision_required', 'blocked'],
  evidence_pending: ['verifying', 'repair_required', 'replan_required', 'blocked'],
  verifying: ['reviewing', 'repair_required', 'replan_required', 'decision_required', 'blocked'],
  reviewing: ['accepted', 'repair_required', 'replan_required', 'decision_required', 'blocked'],
  repair_required: ['eligible', 'cancelled', 'superseded'],
  replan_required: ['planned', 'cancelled', 'superseded'],
  decision_required: ['planned', 'eligible', 'cancelled', 'superseded'],
  blocked: ['planned', 'eligible', 'cancelled', 'superseded'],
  accepted: ['closed'],
  closed: [],
  cancelled: [],
  superseded: [],
};

function requireText(value: string, field: string): string {
  const normalized = value.trim();
  if (normalized.length === 0) {
    throw new DomainValidationError(`${field} must not be empty`);
  }
  return normalized;
}

export function assertWorkPackageTransition(
  from: WorkPackageStatus,
  to: WorkPackageStatus,
): void {
  if (!WORK_PACKAGE_TRANSITIONS[from].includes(to)) {
    throw new InvalidTransitionError(from, to);
  }
}

export function createLifecycleEvent<TPayload extends Record<string, unknown>>(input: {
  id: Identifier;
  projectId: Identifier;
  type: string;
  aggregateType: string;
  aggregateId: Identifier;
  aggregateVersion: number;
  payload: TPayload;
  occurredAt?: Date;
}): LifecycleEvent<TPayload> {
  if (!Number.isInteger(input.aggregateVersion) || input.aggregateVersion < 1) {
    throw new DomainValidationError('aggregateVersion must be a positive integer');
  }
  return {
    ...input,
    id: requireText(input.id, 'event id'),
    projectId: requireText(input.projectId, 'project id'),
    type: requireText(input.type, 'event type'),
    aggregateType: requireText(input.aggregateType, 'aggregate type'),
    aggregateId: requireText(input.aggregateId, 'aggregate id'),
    occurredAt: input.occurredAt ?? new Date(),
  };
}

export function transitionWorkPackage(
  workPackage: WorkPackage,
  to: WorkPackageStatus,
  eventId: Identifier,
  occurredAt = new Date(),
): { readonly workPackage: WorkPackage; readonly event: LifecycleEvent } {
  assertWorkPackageTransition(workPackage.status, to);
  const nextVersion = workPackage.version + 1;
  const transitioned: WorkPackage = {
    ...workPackage,
    status: to,
    version: nextVersion,
    updatedAt: occurredAt,
  };
  return {
    workPackage: transitioned,
    event: createLifecycleEvent({
      id: eventId,
      projectId: workPackage.projectId,
      type: 'work-package.transitioned',
      aggregateType: 'work-package',
      aggregateId: workPackage.id,
      aggregateVersion: nextVersion,
      payload: { from: workPackage.status, to },
      occurredAt,
    }),
  };
}

export function validateProjectGraph(graph: ProjectGraph): void {
  requireText(graph.project.id, 'project id');
  requireText(graph.project.name, 'project name');

  for (const requirement of graph.requirements) {
    if (requirement.projectId !== graph.project.id) {
      throw new DomainValidationError(`Requirement ${requirement.id} belongs to another project`);
    }
    if (requirement.acceptanceCriteria.length === 0) {
      throw new DomainValidationError(`Requirement ${requirement.id} has no acceptance criteria`);
    }
    for (const criterion of requirement.acceptanceCriteria) {
      if (criterion.requirementId !== requirement.id) {
        throw new DomainValidationError(`Acceptance criterion ${criterion.id} belongs to another requirement`);
      }
    }
  }

  for (const plan of graph.plans) {
    if (plan.projectId !== graph.project.id) {
      throw new DomainValidationError(`Plan ${plan.id} belongs to another project`);
    }
    for (const workPackage of plan.workPackages) {
      if (workPackage.projectId !== graph.project.id || workPackage.planId !== plan.id) {
        throw new DomainValidationError(`Work package ${workPackage.id} has an invalid parent`);
      }
    }
  }
}
