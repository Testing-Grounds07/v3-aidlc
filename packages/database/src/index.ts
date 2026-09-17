import {
  assertWorkPackageTransition,
  validateProjectGraph,
  type DeliveryPosture,
  type LifecycleEvent,
  type LifecycleStage,
  type ProjectGraph,
  type WorkPackageStatus as DomainWorkPackageStatus,
} from '@v3/domain';

import {
  PlanStatus,
  PrismaClient,
  ProjectStatus,
  RequirementStatus,
  WorkPackageStatus,
} from './generated/client/index.js';
import type { Prisma } from './generated/client/index.js';

export function createDatabaseClient(): PrismaClient {
  return new PrismaClient();
}

export interface CreateProjectGraphInput {
  readonly project: { readonly id: string; readonly name: string; readonly description: string };
  readonly requirements: readonly {
    readonly id: string;
    readonly title: string;
    readonly description: string;
    readonly acceptanceCriteria: readonly {
      readonly id: string;
      readonly statement: string;
      readonly verificationMethod: string;
    }[];
  }[];
  readonly plans: readonly {
    readonly id: string;
    readonly title: string;
    readonly objective: string;
    readonly workPackages: readonly {
      readonly id: string;
      readonly title: string;
      readonly objective: string;
      readonly intentIds: readonly string[];
      readonly stage: LifecycleStage;
      readonly posture: DeliveryPosture;
      readonly routeInstanceId?: string;
      readonly workstreamId?: string;
      readonly unitId?: string;
      readonly boltId?: string;
      readonly modeId?: string;
      readonly riskProfileId?: string;
      readonly expectedOutcomeTypes: readonly string[];
      readonly promotionTarget?: string;
    }[];
  }[];
}

const toDomainWorkPackageStatus = (status: WorkPackageStatus): DomainWorkPackageStatus =>
  status.toLowerCase() as DomainWorkPackageStatus;

const toDatabaseWorkPackageStatus = (status: DomainWorkPackageStatus): WorkPackageStatus =>
  status.toUpperCase() as WorkPackageStatus;

function payloadRecord(payload: Prisma.JsonValue): Record<string, unknown> {
  return payload !== null && typeof payload === 'object' && !Array.isArray(payload)
    ? (payload as Record<string, unknown>)
    : { value: payload };
}

export class ProjectRepository {
  constructor(private readonly prisma: PrismaClient) {}

  async create(input: CreateProjectGraphInput): Promise<ProjectGraph> {
    await this.prisma.$transaction(async (tx) => {
      const occurredAt = new Date();
      await tx.project.create({
        data: {
          id: input.project.id,
          name: input.project.name,
          description: input.project.description,
          status: ProjectStatus.ACTIVE,
          version: 1,
        },
      });
      await tx.lifecycleEvent.create({
        data: {
          id: `EVT-${input.project.id}-CREATED`,
          projectId: input.project.id,
          type: 'project.created',
          aggregateType: 'project',
          aggregateId: input.project.id,
          aggregateVersion: 1,
          payload: { name: input.project.name },
          occurredAt,
        },
      });

      for (const requirement of input.requirements) {
        await tx.requirement.create({
          data: {
            id: requirement.id,
            projectId: input.project.id,
            title: requirement.title,
            description: requirement.description,
            status: RequirementStatus.APPROVED,
            acceptanceCriteria: {
              create: requirement.acceptanceCriteria.map((criterion) => ({
                id: criterion.id,
                statement: criterion.statement,
                verificationMethod: criterion.verificationMethod,
              })),
            },
          },
        });
        await tx.lifecycleEvent.create({
          data: {
            id: `EVT-${requirement.id}-CREATED`,
            projectId: input.project.id,
            type: 'requirement.created',
            aggregateType: 'requirement',
            aggregateId: requirement.id,
            aggregateVersion: 1,
            payload: { acceptanceCriterionIds: requirement.acceptanceCriteria.map(({ id }) => id) },
            occurredAt,
          },
        });
      }

      for (const plan of input.plans) {
        await tx.plan.create({
          data: {
            id: plan.id,
            projectId: input.project.id,
            title: plan.title,
            objective: plan.objective,
            status: PlanStatus.APPROVED,
          },
        });
        await tx.lifecycleEvent.create({
          data: {
            id: `EVT-${plan.id}-CREATED`,
            projectId: input.project.id,
            type: 'plan.created',
            aggregateType: 'plan',
            aggregateId: plan.id,
            aggregateVersion: 1,
            payload: { workPackageIds: plan.workPackages.map(({ id }) => id) },
            occurredAt,
          },
        });

        for (const workPackage of plan.workPackages) {
          await tx.workPackage.create({
            data: {
              id: workPackage.id,
              projectId: input.project.id,
              planId: plan.id,
              title: workPackage.title,
              objective: workPackage.objective,
              status: WorkPackageStatus.PLANNED,
              intentIds: [...workPackage.intentIds],
              ...(workPackage.routeInstanceId === undefined
                ? {}
                : { routeInstanceId: workPackage.routeInstanceId }),
              ...(workPackage.workstreamId === undefined
                ? {}
                : { workstreamId: workPackage.workstreamId }),
              ...(workPackage.unitId === undefined ? {} : { unitId: workPackage.unitId }),
              ...(workPackage.boltId === undefined ? {} : { boltId: workPackage.boltId }),
              stage: workPackage.stage,
              ...(workPackage.modeId === undefined ? {} : { modeId: workPackage.modeId }),
              posture: workPackage.posture,
              ...(workPackage.riskProfileId === undefined
                ? {}
                : { riskProfileId: workPackage.riskProfileId }),
              expectedOutcomeTypes: [...workPackage.expectedOutcomeTypes],
              ...(workPackage.promotionTarget === undefined
                ? {}
                : { promotionTarget: workPackage.promotionTarget }),
            },
          });
          await tx.lifecycleEvent.create({
            data: {
              id: `EVT-${workPackage.id}-CREATED`,
              projectId: input.project.id,
              type: 'work-package.created',
              aggregateType: 'work-package',
              aggregateId: workPackage.id,
              aggregateVersion: 1,
              payload: { planId: plan.id, stage: workPackage.stage, posture: workPackage.posture },
              occurredAt,
            },
          });
        }
      }
    });

    const graph = await this.get(input.project.id);
    if (graph === null) throw new Error(`Project ${input.project.id} was not persisted`);
    return graph;
  }

  async get(projectId: string): Promise<ProjectGraph | null> {
    const result = await this.prisma.project.findUnique({
      where: { id: projectId },
      include: {
        requirements: { include: { acceptanceCriteria: true }, orderBy: { createdAt: 'asc' } },
        plans: { include: { workPackages: { orderBy: { createdAt: 'asc' } } }, orderBy: { createdAt: 'asc' } },
        events: { orderBy: { sequence: 'asc' } },
      },
    });
    if (result === null) return null;

    const graph: ProjectGraph = {
      project: {
        id: result.id,
        name: result.name,
        description: result.description,
        status: result.status.toLowerCase() as ProjectGraph['project']['status'],
        version: result.version,
        createdAt: result.createdAt,
        updatedAt: result.updatedAt,
      },
      requirements: result.requirements.map((requirement) => ({
        id: requirement.id,
        projectId: requirement.projectId,
        title: requirement.title,
        description: requirement.description,
        status: requirement.status.toLowerCase() as 'draft' | 'approved' | 'superseded',
        version: requirement.version,
        createdAt: requirement.createdAt,
        updatedAt: requirement.updatedAt,
        acceptanceCriteria: requirement.acceptanceCriteria.map((criterion) => ({
          id: criterion.id,
          requirementId: criterion.requirementId,
          statement: criterion.statement,
          verificationMethod: criterion.verificationMethod,
          createdAt: criterion.createdAt,
          updatedAt: criterion.updatedAt,
        })),
      })),
      plans: result.plans.map((plan) => ({
        id: plan.id,
        projectId: plan.projectId,
        title: plan.title,
        objective: plan.objective,
        status: plan.status.toLowerCase() as 'draft' | 'approved' | 'superseded',
        version: plan.version,
        createdAt: plan.createdAt,
        updatedAt: plan.updatedAt,
        workPackages: plan.workPackages.map((workPackage) => ({
          id: workPackage.id,
          projectId: workPackage.projectId,
          planId: workPackage.planId,
          title: workPackage.title,
          objective: workPackage.objective,
          status: toDomainWorkPackageStatus(workPackage.status),
          version: workPackage.version,
          intentIds: workPackage.intentIds,
          ...(workPackage.routeInstanceId === null ? {} : { routeInstanceId: workPackage.routeInstanceId }),
          ...(workPackage.workstreamId === null ? {} : { workstreamId: workPackage.workstreamId }),
          ...(workPackage.unitId === null ? {} : { unitId: workPackage.unitId }),
          ...(workPackage.boltId === null ? {} : { boltId: workPackage.boltId }),
          stage: workPackage.stage as LifecycleStage,
          ...(workPackage.modeId === null ? {} : { modeId: workPackage.modeId }),
          posture: workPackage.posture as DeliveryPosture,
          ...(workPackage.riskProfileId === null ? {} : { riskProfileId: workPackage.riskProfileId }),
          expectedOutcomeTypes: workPackage.expectedOutcomeTypes,
          ...(workPackage.promotionTarget === null ? {} : { promotionTarget: workPackage.promotionTarget }),
          createdAt: workPackage.createdAt,
          updatedAt: workPackage.updatedAt,
        })),
      })),
      events: result.events.map((event): LifecycleEvent => ({
        id: event.id,
        projectId: event.projectId,
        type: event.type,
        aggregateType: event.aggregateType,
        aggregateId: event.aggregateId,
        aggregateVersion: event.aggregateVersion,
        payload: payloadRecord(event.payload),
        occurredAt: event.occurredAt,
      })),
    };
    validateProjectGraph(graph);
    return graph;
  }

  async transitionWorkPackage(
    workPackageId: string,
    to: DomainWorkPackageStatus,
    eventId: string,
  ): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      const current = await tx.workPackage.findUniqueOrThrow({ where: { id: workPackageId } });
      const from = toDomainWorkPackageStatus(current.status);
      assertWorkPackageTransition(from, to);
      const nextVersion = current.version + 1;
      const updated = await tx.workPackage.updateMany({
        where: { id: current.id, version: current.version },
        data: { status: toDatabaseWorkPackageStatus(to), version: nextVersion },
      });
      if (updated.count !== 1) throw new Error(`Concurrent update detected for ${current.id}`);
      await tx.lifecycleEvent.create({
        data: {
          id: eventId,
          projectId: current.projectId,
          type: 'work-package.transitioned',
          aggregateType: 'work-package',
          aggregateId: current.id,
          aggregateVersion: nextVersion,
          payload: { from, to },
        },
      });
    });
  }

  async registerRepository(input: {
    readonly id: string;
    readonly projectId: string;
    readonly rootPath: string;
    readonly defaultBranch: string;
    readonly headRevision: string;
  }): Promise<void> {
    await this.prisma.repositoryRegistration.upsert({
      where: { id: input.id },
      create: input,
      update: {
        rootPath: input.rootPath,
        defaultBranch: input.defaultBranch,
        headRevision: input.headRevision,
      },
    });
  }

  async recordInvestigation(input: {
    readonly id: string;
    readonly projectId: string;
    readonly repositoryId: string;
    readonly task: string;
    readonly artifactPath: string;
    readonly digest: string;
    readonly manifest: Prisma.InputJsonValue;
  }): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      await tx.investigation.create({
        data: { ...input, status: 'completed' },
      });
      await tx.lifecycleEvent.create({
        data: {
          id: `EVT-${input.id}-COMPLETED`,
          projectId: input.projectId,
          type: 'investigation.completed',
          aggregateType: 'investigation',
          aggregateId: input.id,
          aggregateVersion: 1,
          payload: { repositoryId: input.repositoryId, digest: input.digest },
        },
      });
    });
  }

  async recordAgentRun(input: {
    readonly id: string;
    readonly projectId: string;
    readonly workPackageId: string;
    readonly adapterId: string;
    readonly profileId: string;
    readonly requestDigest: string;
    readonly status: 'completed' | 'failed' | 'blocked' | 'cancelled';
    readonly summary: string;
    readonly artifactIds: readonly string[];
    readonly evidenceIds: readonly string[];
    readonly findingIds: readonly string[];
    readonly satisfiedCriteria: readonly string[];
    readonly usage: Prisma.InputJsonValue;
    readonly providerResultRef: string;
    readonly startedAt: Date;
    readonly finishedAt: Date;
  }): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      await tx.agentRun.create({
        data: {
          ...input,
          artifactIds: [...input.artifactIds],
          evidenceIds: [...input.evidenceIds],
          findingIds: [...input.findingIds],
          satisfiedCriteria: [...input.satisfiedCriteria],
        },
      });
      await tx.lifecycleEvent.create({
        data: {
          id: `EVT-${input.id}-${input.status.toUpperCase()}`,
          projectId: input.projectId,
          type: `agent-run.${input.status}`,
          aggregateType: 'agent-run',
          aggregateId: input.id,
          aggregateVersion: 1,
          payload: {
            workPackageId: input.workPackageId,
            adapterId: input.adapterId,
            requestDigest: input.requestDigest,
          },
        },
      });
    });
  }

  async recordEvidence(input: {
    readonly id: string;
    readonly projectId: string;
    readonly workPackageId: string;
    readonly kind: string;
    readonly subjectRevision: string;
    readonly producerId: string;
    readonly producerRole: string;
    readonly producerIndependenceGroup: string;
    readonly collectedAt: Date;
    readonly locator: string;
    readonly sha256: string;
    readonly assertions: readonly string[];
  }): Promise<void> {
    await this.prisma.evidenceRecord.create({ data: { ...input, assertions: [...input.assertions] } });
  }

  async recordGateDecision(input: {
    readonly id: string;
    readonly projectId: string;
    readonly workPackageId: string;
    readonly revision: string;
    readonly attempt: number;
    readonly outcome: 'passed' | 'failed' | 'inconclusive';
    readonly promotable: boolean;
    readonly reasons: readonly string[];
    readonly evidenceIds: readonly string[];
  }): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      await tx.gateDecision.create({
        data: { ...input, reasons: [...input.reasons], evidenceIds: [...input.evidenceIds] },
      });
      await tx.lifecycleEvent.create({
        data: {
          id: `EVT-${input.id}`,
          projectId: input.projectId,
          type: 'gate.evaluated',
          aggregateType: 'gate-decision',
          aggregateId: input.id,
          aggregateVersion: 1,
          payload: { workPackageId: input.workPackageId, revision: input.revision, outcome: input.outcome },
        },
      });
    });
  }

  async recordWorktreeSession(input: {
    readonly id: string;
    readonly projectId: string;
    readonly workPackageId: string;
    readonly repositoryRoot: string;
    readonly worktreePath: string;
    readonly branch: string;
    readonly baseRevision: string;
    readonly headRevision: string;
  }): Promise<void> {
    await this.prisma.worktreeSession.create({ data: input });
  }

  async recordChangeProposal(input: {
    readonly id: string;
    readonly projectId: string;
    readonly workPackageId: string;
    readonly worktreeSessionId: string;
    readonly title: string;
    readonly body: string;
    readonly baseRevision: string;
    readonly headRevision: string;
    readonly branch: string;
    readonly changedFiles: readonly string[];
    readonly verificationEvidenceIds: readonly string[];
    readonly digest: string;
  }): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      await tx.changeProposal.create({
        data: {
          ...input,
          changedFiles: [...input.changedFiles],
          verificationEvidenceIds: [...input.verificationEvidenceIds],
        },
      });
      await tx.lifecycleEvent.create({
        data: {
          id: `EVT-${input.id}-PREPARED`,
          projectId: input.projectId,
          type: 'change-proposal.prepared',
          aggregateType: 'change-proposal',
          aggregateId: input.id,
          aggregateVersion: 1,
          payload: {
            workPackageId: input.workPackageId,
            baseRevision: input.baseRevision,
            headRevision: input.headRevision,
            digest: input.digest,
          },
        },
      });
    });
  }

  async recordGitHubPullRequest(input: {
    readonly id: string;
    readonly projectId: string;
    readonly workPackageId: string;
    readonly changeProposalId: string;
    readonly repository: string;
    readonly number: number;
    readonly url: string;
    readonly baseBranch: string;
    readonly headBranch: string;
    readonly headRevision: string;
    readonly state: 'open' | 'closed' | 'merged';
  }): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      await tx.gitHubPullRequest.create({ data: input });
      await tx.changeProposal.update({
        where: { id: input.changeProposalId },
        data: { status: 'published', externalUrl: input.url },
      });
      await tx.lifecycleEvent.create({
        data: {
          id: `EVT-${input.id}-OPENED`,
          projectId: input.projectId,
          type: 'pull-request.opened',
          aggregateType: 'pull-request',
          aggregateId: input.id,
          aggregateVersion: 1,
          payload: {
            repository: input.repository,
            number: input.number,
            headRevision: input.headRevision,
          },
        },
      });
    });
  }

  async recordDecisionRequest(input: {
    readonly id: string; readonly projectId: string; readonly actionId: string;
    readonly headline: string; readonly explanation: string; readonly impact: string;
    readonly actionNeeded: string; readonly question: string; readonly options: Prisma.InputJsonValue;
    readonly recommendedOptionId?: string; readonly unaffectedWork: string; readonly requestedAt: Date;
  }): Promise<void> {
    await this.prisma.decisionRequest.create({ data: input });
  }

  async recordHumanDecision(input: {
    readonly id: string; readonly projectId: string; readonly decisionRequestId: string;
    readonly selectedOptionId: string; readonly userWords: string; readonly submittedAt: Date;
  }): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      await tx.humanDecision.create({ data: input });
      await tx.decisionRequest.update({ where: { id: input.decisionRequestId }, data: { status: 'resolved' } });
      await tx.lifecycleEvent.create({
        data: {
          id: `EVT-${input.id}-RECORDED`, projectId: input.projectId,
          type: 'human-decision.recorded', aggregateType: 'human-decision', aggregateId: input.id,
          aggregateVersion: 1, payload: { decisionRequestId: input.decisionRequestId, selectedOptionId: input.selectedOptionId },
        },
      });
    });
  }

  async recordStandingDelegation(input: {
    readonly id: string; readonly projectId: string; readonly grantedBy: string;
    readonly actionTypes: readonly string[]; readonly targets: readonly string[];
    readonly requiredEvidence: readonly string[]; readonly policyVersion: string;
    readonly userWords: string; readonly grantedAt: Date; readonly expiresAt?: Date;
  }): Promise<void> {
    await this.prisma.standingDelegation.create({
      data: { ...input, actionTypes: [...input.actionTypes], targets: [...input.targets], requiredEvidence: [...input.requiredEvidence] },
    });
  }

  async revokeStandingDelegation(input: {
    readonly projectId: string; readonly delegationId: string; readonly revokedAt: Date; readonly userWords: string;
  }): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      const updated = await tx.standingDelegation.updateMany({
        where: { id: input.delegationId, projectId: input.projectId, revokedAt: null },
        data: { revokedAt: input.revokedAt, revocationWords: input.userWords },
      });
      if (updated.count !== 1) throw new Error('Delegation is missing or already revoked');
      await tx.lifecycleEvent.create({
        data: {
          id: `EVT-${input.delegationId}-REVOKED`, projectId: input.projectId,
          type: 'delegation.revoked', aggregateType: 'standing-delegation', aggregateId: input.delegationId,
          aggregateVersion: 2, payload: { revokedAt: input.revokedAt.toISOString() },
        },
      });
    });
  }
}
