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

  it('persists a normalized provider-neutral agent result without raw output', async () => {
    await repository.recordAgentRun({
      id: 'RUN-M3-1',
      projectId,
      workPackageId: 'WP-M1-1',
      adapterId: 'codex',
      profileId: 'PROFILE-CODEX',
      requestDigest: 'c'.repeat(64),
      status: 'completed',
      summary: 'Implemented the bounded change',
      artifactIds: ['ART-1'],
      evidenceIds: ['EVD-1'],
      findingIds: [],
      satisfiedCriteria: ['AC-M1-1'],
      usage: { inputTokens: 10, outputTokens: 20 },
      providerResultRef: 'provider-result://run-m3-1',
      startedAt: new Date('2026-09-17T00:00:00Z'),
      finishedAt: new Date('2026-09-17T00:00:01Z'),
    });

    const run = await prisma.agentRun.findUniqueOrThrow({ where: { id: 'RUN-M3-1' } });
    expect(run).toMatchObject({ status: 'completed', adapterId: 'codex', evidenceIds: ['EVD-1'] });
  });

  it('persists revision-bound evidence and the gate decision', async () => {
    await repository.recordEvidence({
      id: 'EVID-M4-1', projectId, workPackageId: 'WP-M1-1', kind: 'test_result',
      subjectRevision: 'revision-m4', producerId: 'verification-engine', producerRole: 'verifier',
      producerIndependenceGroup: 'deterministic-runtime', collectedAt: new Date('2026-09-17T00:00:02Z'),
      locator: `sha256:${'d'.repeat(64)}`, sha256: 'd'.repeat(64), assertions: ['Unit tests: passed'],
    });
    await repository.recordGateDecision({
      id: 'GATE-M4-1', projectId, workPackageId: 'WP-M1-1', revision: 'revision-m4', attempt: 0,
      outcome: 'passed', promotable: true, reasons: [], evidenceIds: ['EVID-M4-1'],
    });
    expect(await prisma.evidenceRecord.findUnique({ where: { id: 'EVID-M4-1' } })).toMatchObject({ subjectRevision: 'revision-m4' });
    expect(await prisma.gateDecision.findUnique({ where: { id: 'GATE-M4-1' } })).toMatchObject({ outcome: 'passed', promotable: true });
  });

  it('persists an isolated worktree and review-ready proposal', async () => {
    await repository.recordWorktreeSession({
      id: 'WT-M5-1', projectId, workPackageId: 'WP-M1-1', repositoryRoot: '/repo',
      worktreePath: '/worktrees/wp-m1-1', branch: 'v3/wp-m1-1', baseRevision: 'base-rev', headRevision: 'head-rev',
    });
    await repository.recordChangeProposal({
      id: 'PROP-M5-1', projectId, workPackageId: 'WP-M1-1', worktreeSessionId: 'WT-M5-1',
      title: 'Prepare isolated change', body: 'Summary and verification', baseRevision: 'base-rev',
      headRevision: 'head-rev', branch: 'v3/wp-m1-1', changedFiles: ['feature.ts'],
      verificationEvidenceIds: ['EVID-M4-1'], digest: 'e'.repeat(64),
    });
    expect(await prisma.changeProposal.findUnique({ where: { id: 'PROP-M5-1' } })).toMatchObject({
      status: 'prepared', changedFiles: ['feature.ts'],
    });
  });

  it('persists a GitHub pull request at the verified revision', async () => {
    await repository.recordGitHubPullRequest({
      id: 'PR-M6-1', projectId, workPackageId: 'WP-M1-1', changeProposalId: 'PROP-M5-1',
      repository: 'owner/repo', number: 1, url: 'https://github.test/owner/repo/pull/1',
      baseBranch: 'main', headBranch: 'v3/wp-m1-1', headRevision: 'head-rev', state: 'open',
    });
    expect(await prisma.gitHubPullRequest.findUnique({ where: { id: 'PR-M6-1' } })).toMatchObject({
      number: 1, headRevision: 'head-rev', state: 'open',
    });
    expect(await prisma.changeProposal.findUnique({ where: { id: 'PROP-M5-1' } })).toMatchObject({
      status: 'published', externalUrl: 'https://github.test/owner/repo/pull/1',
    });
  });

  it('persists human decisions and immediately revokes standing authority', async () => {
    await repository.recordDecisionRequest({
      id: 'DR-M7-1', projectId, actionId: 'ACTION-DEPLOY', headline: 'Choose where to release',
      explanation: 'The release affects other people.', impact: 'The choice controls exposure.',
      actionNeeded: 'Choose one option.', question: 'Release to staging?',
      options: [{ id: 'yes', label: 'Staging', tradeoff: 'Internal only.' }, { id: 'no', label: 'Stop', tradeoff: 'No release.' }],
      recommendedOptionId: 'yes', unaffectedWork: 'Other work can continue.', requestedAt: new Date('2026-09-17T00:00:00Z'),
    });
    await repository.recordHumanDecision({
      id: 'DEC-M7-1', projectId, decisionRequestId: 'DR-M7-1', selectedOptionId: 'yes',
      userWords: 'Use staging.', submittedAt: new Date('2026-09-17T00:01:00Z'),
    });
    await repository.recordStandingDelegation({
      id: 'DEL-M7-1', projectId, grantedBy: 'user-1', actionTypes: ['deploy'], targets: ['staging'],
      requiredEvidence: ['EVID-M4-1'], policyVersion: '1.0.0', userWords: 'Deploy after checks pass.',
      grantedAt: new Date('2026-09-17T00:01:00Z'),
    });
    await repository.revokeStandingDelegation({
      projectId, delegationId: 'DEL-M7-1', revokedAt: new Date('2026-09-17T00:02:00Z'), userWords: 'Stop automatic deploys.',
    });
    expect(await prisma.decisionRequest.findUnique({ where: { id: 'DR-M7-1' } })).toMatchObject({ status: 'resolved' });
    expect(await prisma.standingDelegation.findUnique({ where: { id: 'DEL-M7-1' } })).toMatchObject({ revocationWords: 'Stop automatic deploys.' });
  });

  it('projects durable project state into the plain dashboard view', async () => {
    const dashboard = await repository.getDashboard(projectId);
    expect(dashboard).toMatchObject({
      project: { id: projectId, name: 'Milestone 1' },
      summary: { waiting: 1 },
      evidence: { passed: 1, failed: 0 },
    });
    expect(dashboard?.work[0]).toMatchObject({ id: 'WP-M1-1', stage: 'implementation' });
    expect(dashboard?.decisions).toHaveLength(0);
  });

  it('persists and reloads a segmented process health report', async () => {
    const metric = { value: 0.8, unit: 'ratio' as const, sampleSize: 5, status: 'healthy' as const, explanation: 'Healthy sample.' };
    await repository.recordProcessHealthReport({
      id: 'HEALTH-M9-1', projectId, windowStart: new Date('2026-09-01'), windowEnd: new Date('2026-10-01'),
      dimensions: { mode: 'feature' },
      metrics: {
        firstPassYield: metric,
        medianCycleTime: { ...metric, value: 86_400_000, unit: 'milliseconds' },
        repairRate: { ...metric, value: 0.2, unit: 'count' },
        medianDecisionWait: { ...metric, value: 1000, unit: 'milliseconds' },
        blockedShare: { ...metric, value: 0.05 },
      },
      recommendations: [],
    });
    expect(await repository.getLatest(projectId)).toMatchObject({
      projectId, dimensions: { mode: 'feature' }, metrics: { firstPassYield: { status: 'healthy' } },
    });
  });
});
