import { describe, expect, it } from 'vitest';

import { GitHubIntegration, GitHubIntegrationError, evaluateCiGate, type CheckSnapshot, type GitHubClient } from './index.js';
import type { ChangeProposal } from '@v3/workspace';

const proposal: ChangeProposal = {
  id: 'PROP-1', workPackageId: 'WP-1', title: 'Bounded change', body: 'Summary',
  baseRevision: 'base', headRevision: 'head', branch: 'v3/wp-1', changedFiles: ['feature.ts'],
  verificationEvidenceIds: ['EVID-LOCAL'], digest: 'a'.repeat(64),
};

function client(checks: readonly CheckSnapshot[] = [], remoteRevision = 'head'): GitHubClient {
  return {
    async publishBranch() { return { remoteRevision }; },
    async createPullRequest(input) {
      return { number: 1, url: 'https://github.test/o/r/pull/1', repository: input.repository, baseBranch: input.baseBranch, headBranch: input.headBranch, headRevision: remoteRevision, state: 'open' };
    },
    async listChecks() { return checks; },
  };
}

const check = (name: string, conclusion: CheckSnapshot['conclusion'], status: CheckSnapshot['status'] = 'completed'): CheckSnapshot => ({
  id: name.toLowerCase(), name, url: `https://github.test/checks/${name}`, headRevision: 'head', status, conclusion,
  startedAt: new Date('2026-09-17T00:00:00Z'), ...(status === 'completed' ? { completedAt: new Date('2026-09-17T00:01:00Z') } : {}),
});

describe('GitHubIntegration', () => {
  it('publishes and opens a pull request only for the verified head', async () => {
    await expect(new GitHubIntegration(client()).publish({ repository: 'owner/repo', baseBranch: 'main', proposal })).resolves.toMatchObject({ number: 1, headRevision: 'head' });
  });

  it('fails closed when the remote branch revision drifts', async () => {
    await expect(new GitHubIntegration(client([], 'other')).publish({ repository: 'owner/repo', baseBranch: 'main', proposal })).rejects.toThrow(GitHubIntegrationError);
  });

  it('normalizes CI checks into revision-bound evidence', async () => {
    const integration = new GitHubIntegration(client([check('verify', 'success')]));
    const evidence = await integration.collectCiEvidence({
      repository: 'owner/repo', workPackageId: 'WP-1',
      pullRequest: { number: 1, url: 'url', repository: 'owner/repo', baseBranch: 'main', headBranch: 'v3/wp-1', headRevision: 'head', state: 'open' },
    });
    expect(evidence[0]).toMatchObject({ subjectRevision: 'head', assertions: ['verify: passed'] });
    expect(evaluateCiGate({ requiredChecks: ['verify'], headRevision: 'head', evidence })).toMatchObject({ outcome: 'passed', promotable: true });
  });

  it('keeps pending or missing CI inconclusive and failed CI non-promotable', async () => {
    const pr = { number: 1, url: 'url', repository: 'owner/repo', baseBranch: 'main', headBranch: 'v3/wp-1', headRevision: 'head', state: 'open' as const };
    const pending = await new GitHubIntegration(client([check('verify', null, 'in_progress')])).collectCiEvidence({ repository: 'owner/repo', pullRequest: pr, workPackageId: 'WP-1' });
    expect(evaluateCiGate({ requiredChecks: ['verify'], headRevision: 'head', evidence: pending }).outcome).toBe('inconclusive');
    const failed = await new GitHubIntegration(client([check('verify', 'failure')])).collectCiEvidence({ repository: 'owner/repo', pullRequest: pr, workPackageId: 'WP-1' });
    expect(evaluateCiGate({ requiredChecks: ['verify'], headRevision: 'head', evidence: failed }).outcome).toBe('failed');
  });
});
