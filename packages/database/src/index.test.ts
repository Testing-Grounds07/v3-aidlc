import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { ProjectRepository, createDatabaseClient } from './index.js';

const hasDatabase = Boolean(process.env.DATABASE_URL);
const prisma = createDatabaseClient();
const repository = new ProjectRepository(prisma);
const projectId = 'PRJ-M1-INTEGRATION';

describe.skipIf(!hasDatabase)('ProjectRepository PostgreSQL integration', () => {
  beforeAll(async () => {
    await prisma.project.deleteMany({ where: { id: projectId } });
  });

  afterAll(async () => {
    await prisma.project.deleteMany({ where: { id: projectId } });
    await prisma.$disconnect();
  });

  it('persists and reloads the governed project chain with events', async () => {
    const created = await repository.create({
      project: { id: projectId, name: 'Milestone 1', description: 'Domain persistence proof' },
      requirements: [{
        id: 'REQ-M1-1',
        title: 'Reload durable state',
        description: 'The complete project chain survives a database round trip.',
        acceptanceCriteria: [{
          id: 'AC-M1-1',
          statement: 'Project, requirement, criterion, plan, and work package reload.',
          verificationMethod: 'PostgreSQL integration test',
        }],
      }],
      plans: [{
        id: 'PLAN-M1-1',
        title: 'Persistence vertical slice',
        objective: 'Prove the minimum governed chain',
        workPackages: [{
          id: 'WP-M1-1',
          title: 'Persist the graph',
          objective: 'Create and reload all Milestone 1 entities',
          intentIds: ['INT-M1-1'],
          routeInstanceId: 'ROUTE-M1-1',
          workstreamId: 'WS-M1-1',
          unitId: 'UNIT-M1-1',
          boltId: 'BOLT-M1-1',
          stage: 'implementation',
          modeId: 'MODE-FEATURE-DEVELOPMENT',
          posture: 'balanced',
          riskProfileId: 'RISK-M1-1',
          expectedOutcomeTypes: ['accepted_result'],
          promotionTarget: 'milestone-2',
        }],
      }],
    });

    expect(created.requirements[0]?.acceptanceCriteria[0]?.id).toBe('AC-M1-1');
    expect(created.plans[0]?.workPackages[0]).toMatchObject({
      id: 'WP-M1-1',
      status: 'planned',
      stage: 'implementation',
      posture: 'balanced',
    });
    expect(created.events.map(({ type }) => type)).toEqual([
      'project.created',
      'requirement.created',
      'plan.created',
      'work-package.created',
    ]);
  });

  it('persists a guarded transition and reloads its event', async () => {
    await repository.transitionWorkPackage('WP-M1-1', 'eligible', 'EVT-WP-M1-ELIGIBLE');
    const reloaded = await repository.get(projectId);

    expect(reloaded?.plans[0]?.workPackages[0]).toMatchObject({ status: 'eligible', version: 2 });
    expect(reloaded?.events.at(-1)).toMatchObject({
      id: 'EVT-WP-M1-ELIGIBLE',
      type: 'work-package.transitioned',
      aggregateVersion: 2,
      payload: { from: 'planned', to: 'eligible' },
    });
  });

  it('registers a repository and persists a structured investigation reference', async () => {
    await repository.registerRepository({
      id: 'REPO-M1-1',
      projectId,
      rootPath: '/workspace/v3-aidlc',
      defaultBranch: 'main',
      headRevision: 'a'.repeat(40),
    });
    await repository.recordInvestigation({
      id: 'INV-M2-1',
      projectId,
      repositoryId: 'REPO-M1-1',
      task: 'Inspect persistence',
      artifactPath: 'investigations/abc.json',
      digest: 'b'.repeat(64),
      manifest: { relevantFiles: ['prisma/schema.prisma'], contextBytes: 1024 },
    });

    const investigation = await prisma.investigation.findUniqueOrThrow({ where: { id: 'INV-M2-1' } });
    expect(investigation).toMatchObject({
      repositoryId: 'REPO-M1-1',
      status: 'completed',
      digest: 'b'.repeat(64),
    });
  });
});
