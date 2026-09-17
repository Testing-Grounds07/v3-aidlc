import { createHash } from 'node:crypto';

import type { EvidenceRecord, GateEvaluation } from '@v3/verification';
import type { ChangeProposal } from '@v3/workspace';

export class GitHubIntegrationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'GitHubIntegrationError';
  }
}

export interface PullRequestSnapshot {
  readonly number: number;
  readonly url: string;
  readonly repository: string;
  readonly baseBranch: string;
  readonly headBranch: string;
  readonly headRevision: string;
  readonly state: 'open' | 'closed' | 'merged';
}

export interface CheckSnapshot {
  readonly id: string;
  readonly name: string;
  readonly url: string;
  readonly headRevision: string;
  readonly status: 'queued' | 'in_progress' | 'completed';
  readonly conclusion: 'success' | 'failure' | 'cancelled' | 'timed_out' | 'neutral' | 'skipped' | null;
  readonly startedAt: Date;
  readonly completedAt?: Date;
}

export interface GitHubClient {
  publishBranch(input: { readonly repository: string; readonly branch: string; readonly headRevision: string }): Promise<{ readonly remoteRevision: string }>;
  createPullRequest(input: { readonly repository: string; readonly baseBranch: string; readonly headBranch: string; readonly title: string; readonly body: string }): Promise<PullRequestSnapshot>;
  listChecks(input: { readonly repository: string; readonly headRevision: string }): Promise<readonly CheckSnapshot[]>;
}

export class GitHubIntegration {
  constructor(private readonly client: GitHubClient) {}

  async publish(input: {
    readonly repository: string;
    readonly baseBranch: string;
    readonly proposal: ChangeProposal;
  }): Promise<PullRequestSnapshot> {
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(input.repository)) throw new GitHubIntegrationError('Repository must use owner/name form');
    const published = await this.client.publishBranch({
      repository: input.repository,
      branch: input.proposal.branch,
      headRevision: input.proposal.headRevision,
    });
    if (published.remoteRevision !== input.proposal.headRevision) throw new GitHubIntegrationError('Published branch does not match the verified proposal revision');
    const pullRequest = await this.client.createPullRequest({
      repository: input.repository,
      baseBranch: input.baseBranch,
      headBranch: input.proposal.branch,
      title: input.proposal.title,
      body: input.proposal.body,
    });
    if (pullRequest.headRevision !== input.proposal.headRevision) throw new GitHubIntegrationError('Pull request head does not match the verified proposal revision');
    return pullRequest;
  }

  async collectCiEvidence(input: {
    readonly repository: string;
    readonly pullRequest: PullRequestSnapshot;
    readonly workPackageId: string;
    readonly now?: Date;
  }): Promise<readonly EvidenceRecord[]> {
    const checks = await this.client.listChecks({ repository: input.repository, headRevision: input.pullRequest.headRevision });
    return checks.map((check) => {
      if (check.headRevision !== input.pullRequest.headRevision) throw new GitHubIntegrationError(`Check ${check.name} is for a different revision`);
      const assertion = check.status !== 'completed' ? 'pending' : check.conclusion === 'success' ? 'passed' : check.conclusion ?? 'inconclusive';
      const canonical = JSON.stringify({ id: check.id, name: check.name, headRevision: check.headRevision, status: check.status, conclusion: check.conclusion, url: check.url });
      const sha256 = createHash('sha256').update(canonical).digest('hex');
      return {
        id: `EVID-CI-${check.id.toUpperCase().replace(/[^A-Z0-9-]/g, '-')}`,
        kind: 'test_result',
        subjectId: input.workPackageId,
        subjectRevision: check.headRevision,
        producerId: `github-check:${check.id}`,
        producerRole: 'ci',
        producerIndependenceGroup: 'github-actions',
        collectedAt: input.now ?? check.completedAt ?? new Date(),
        locator: check.url,
        sha256,
        assertions: [`${check.name}: ${assertion}`],
      } satisfies EvidenceRecord;
    });
  }
}

export function evaluateCiGate(input: {
  readonly requiredChecks: readonly string[];
  readonly headRevision: string;
  readonly evidence: readonly EvidenceRecord[];
}): GateEvaluation {
  const reasons: string[] = [];
  let failed = false;
  const matched: EvidenceRecord[] = [];
  for (const name of input.requiredChecks) {
    const prefix = `${name}: `;
    const record = input.evidence.find((item) => item.assertions.some((assertion) => assertion.startsWith(prefix)));
    if (record === undefined) {
      reasons.push(`${name} has no CI result`);
      continue;
    }
    matched.push(record);
    if (record.subjectRevision !== input.headRevision) reasons.push(`${name} result is stale`);
    const assertion = record.assertions.find((item) => item.startsWith(prefix));
    if (assertion === `${name}: pending`) reasons.push(`${name} is still running`);
    else if (assertion !== `${name}: passed`) failed = true;
  }
  if (failed) return { outcome: 'failed', promotable: false, reasons, evidenceIds: matched.map(({ id }) => id) };
  if (reasons.length > 0) return { outcome: 'inconclusive', promotable: false, reasons, evidenceIds: matched.map(({ id }) => id) };
  return { outcome: 'passed', promotable: true, reasons: [], evidenceIds: matched.map(({ id }) => id) };
}
