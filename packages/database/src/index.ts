import {
  assertWorkPackageTransition,
  validateProjectGraph,
  type DeliveryPosture,
  type LifecycleEvent,
  type LifecycleStage,
  type ProjectGraph,
  type WorkPackageStatus as DomainWorkPackageStatus,
} from '@v3/domain';
import { summarizeWork, type DashboardService, type ProjectDashboard } from '@v3/dashboard';
import type { ProcessHealthReport as HealthReport, ProcessHealthService } from '@v3/analytics';
import type { EvaluationResult as ProviderEvaluationResult, ProviderBenchmark as ProviderBenchmarkRecord } from '@v3/evaluations';

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

export class ProjectRepository implements DashboardService, ProcessHealthService {
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

  async getDashboard(projectId: string): Promise<ProjectDashboard | null> {
    const project = await this.prisma.project.findUnique({
      where: { id: projectId },
      include: {
        workPackages: { orderBy: { updatedAt: 'desc' } },
        evidence: { orderBy: { collectedAt: 'desc' } },
        decisionRequests: { where: { status: 'pending' }, orderBy: { requestedAt: 'asc' } },
      },
    });
    if (project === null) return null;
    const progress: Readonly<Record<string, number>> = {
      PROPOSED: 5, PLANNED: 10, ELIGIBLE: 15, LEASED: 20, RUNNING: 45,
      EVIDENCE_PENDING: 65, VERIFYING: 75, REVIEWING: 85, REPAIR_REQUIRED: 55,
      REPLAN_REQUIRED: 20, DECISION_REQUIRED: 50, BLOCKED: 50, ACCEPTED: 95, CLOSED: 100,
      CANCELLED: 100, SUPERSEDED: 100,
    };
    const work = project.workPackages.map((item) => ({
      id: item.id, title: item.title, workstream: item.workstreamId ?? 'Primary workstream',
      stage: item.stage, mode: item.modeId ?? 'Standard delivery', posture: item.posture,
      status: item.status.toLowerCase(), progress: progress[item.status] ?? 0,
      summary: item.objective, lastUpdatedAt: item.updatedAt,
    }));
    const passed = project.evidence.filter(({ assertions }) => assertions.some((value) => value.endsWith(': passed') || value === 'approved')).length;
    const failed = project.evidence.filter(({ assertions }) => assertions.some((value) => /: (failed|failure|cancelled|timed_out)$/.test(value) || value === 'changes_requested')).length;
    const inconclusive = Math.max(0, project.evidence.length - passed - failed);
    return {
      project: { id: project.id, name: project.name, outcome: project.description, status: project.status.toLowerCase() },
      summary: summarizeWork(work),
      work,
      decisions: project.decisionRequests.map((decision) => ({
        id: decision.id, headline: decision.headline, question: decision.question, impact: decision.impact,
        optionCount: Array.isArray(decision.options) ? decision.options.length : 0, requestedAt: decision.requestedAt,
      })),
      evidence: { passed, failed, inconclusive, updatedAt: project.evidence[0]?.collectedAt ?? project.updatedAt },
    };
  }

  async recordProcessHealthReport(input: HealthReport & { readonly id: string }): Promise<void> {
    await this.prisma.processHealthReport.create({
      data: {
        id: input.id, projectId: input.projectId, windowStart: input.windowStart, windowEnd: input.windowEnd,
        dimensions: JSON.parse(JSON.stringify(input.dimensions)) as Prisma.InputJsonValue,
        metrics: JSON.parse(JSON.stringify(input.metrics)) as Prisma.InputJsonValue,
        recommendations: [...input.recommendations],
      },
    });
  }

  async getLatest(projectId: string): Promise<HealthReport | null> {
    const report = await this.prisma.processHealthReport.findFirst({ where: { projectId }, orderBy: { windowEnd: 'desc' } });
    if (report === null) return null;
    return {
      projectId: report.projectId, windowStart: report.windowStart, windowEnd: report.windowEnd,
      dimensions: report.dimensions as HealthReport['dimensions'], metrics: report.metrics as unknown as HealthReport['metrics'],
      recommendations: report.recommendations,
    };
  }

  async recordEvaluationResult(input: ProviderEvaluationResult & {
    readonly id: string; readonly projectId: string; readonly caseVersion: string;
    readonly contextRevision: string; readonly profileId: string;
  }): Promise<void> {
    await this.prisma.evaluationResult.create({
      data: {
        ...input,
        scores: JSON.parse(JSON.stringify(input.scores)) as Prisma.InputJsonValue,
        failures: [...input.failures],
      },
    });
  }

  async recordProviderBenchmark(input: ProviderBenchmarkRecord & { readonly id: string; readonly projectId: string }): Promise<void> {
    await this.prisma.providerBenchmark.create({ data: input });
  }

  async createOrganization(input: {
    readonly id: string; readonly name: string; readonly slug: string;
    readonly team: { readonly id: string; readonly name: string; readonly slug: string };
  }): Promise<void> {
    await this.prisma.organization.create({
      data: { id: input.id, name: input.name, slug: input.slug, teams: { create: input.team } },
    });
  }

  async assignProjectToTeam(input: { readonly projectId: string; readonly organizationId: string; readonly teamId: string }): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      const team = await tx.team.findUniqueOrThrow({ where: { id: input.teamId } });
      if (team.organizationId !== input.organizationId) throw new Error('Team does not belong to the organization');
      await tx.project.update({ where: { id: input.projectId }, data: { organizationId: input.organizationId, teamId: input.teamId } });
    });
  }

  async addMembership(input: {
    readonly id: string; readonly organizationId: string; readonly teamId?: string;
    readonly principalId: string; readonly organizationRole: string; readonly teamRole?: string;
    readonly status: 'invited' | 'active' | 'suspended' | 'removed'; readonly expiresAt?: Date;
  }): Promise<void> {
    if (input.teamId !== undefined) {
      const team = await this.prisma.team.findUniqueOrThrow({ where: { id: input.teamId } });
      if (team.organizationId !== input.organizationId) throw new Error('Membership team does not belong to the organization');
    }
    await this.prisma.membership.create({ data: input });
  }

  async setOrganizationQuota(input: {
    readonly id: string; readonly organizationId: string; readonly dimension: string; readonly maximum: number;
  }): Promise<void> {
    if (!Number.isFinite(input.maximum) || input.maximum < 0) throw new Error('Quota maximum must be non-negative');
    await this.prisma.organizationQuota.create({ data: input });
  }

  async consumeOrganizationQuota(organizationId: string, dimension: string, amount: number): Promise<void> {
    if (!Number.isFinite(amount) || amount < 0) throw new Error('Quota consumption must be non-negative');
    await this.prisma.$transaction(async (tx) => {
      const quota = await tx.organizationQuota.findUniqueOrThrow({ where: { organizationId_dimension: { organizationId, dimension } } });
      if (quota.used + amount > quota.maximum) throw new Error(`Organization quota exceeded for ${dimension}`);
      const updated = await tx.organizationQuota.updateMany({
        where: { id: quota.id, version: quota.version, used: quota.used },
        data: { used: { increment: amount }, version: { increment: 1 } },
      });
      if (updated.count !== 1) throw new Error('Concurrent quota update detected');
    });
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
