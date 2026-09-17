import { describe, expect, it } from 'vitest';
import { authorizeProjectAction, checkQuota, inheritPolicy, type Membership } from './index.js';

const membership: Membership = { id: 'MEM-1', organizationId: 'ORG-1', teamId: 'TEAM-1', principalId: 'USER-1', organizationRole: 'member', teamRole: 'contributor', status: 'active' };
const project = { projectId: 'PRJ-1', organizationId: 'ORG-1', teamId: 'TEAM-1' };

describe('organization authorization', () => {
  it('allows only explicit active membership in the project tenant and team', () => {
    expect(authorizeProjectAction({ principalId: 'USER-1', project, permission: 'work:execute', memberships: [membership], now: new Date() }).allowed).toBe(true);
    expect(authorizeProjectAction({ principalId: 'USER-1', project: { ...project, organizationId: 'ORG-2' }, permission: 'project:view', memberships: [membership], now: new Date() }).allowed).toBe(false);
    expect(authorizeProjectAction({ principalId: 'USER-1', project, permission: 'decision:approve', memberships: [membership], now: new Date() }).allowed).toBe(false);
  });
  it('prevents a reviewer from approving work from the same independence group', () => {
    const reviewer = { ...membership, teamRole: 'reviewer' as const };
    expect(authorizeProjectAction({ principalId: 'USER-1', project, permission: 'work:review', memberships: [reviewer], now: new Date(), producerIndependenceGroup: 'team-a', reviewerIndependenceGroup: 'team-a' }).allowed).toBe(false);
  });
  it('treats suspension and expiration as immediate loss of authority', () => {
    expect(authorizeProjectAction({ principalId: 'USER-1', project, permission: 'project:view', memberships: [{ ...membership, status: 'suspended' }], now: new Date() }).allowed).toBe(false);
    expect(authorizeProjectAction({ principalId: 'USER-1', project, permission: 'project:view', memberships: [{ ...membership, expiresAt: new Date(0) }], now: new Date() }).allowed).toBe(false);
  });
});

describe('organization controls', () => {
  it('inherits the stricter maximum and every non-waivable control', () => {
    expect(inheritPolicy(
      { id: 'ORG', version: '1', nonWaivableControls: ['security'], maximums: { cost: 100, parallel: 4 } },
      { id: 'PRJ', version: '2', nonWaivableControls: ['privacy'], maximums: { cost: 200, parallel: 2 } },
    )).toMatchObject({ nonWaivableControls: ['privacy', 'security'], maximums: { cost: 100, parallel: 2 } });
  });
  it('fails closed on missing or exhausted quota dimensions', () => {
    expect(checkQuota([{ dimension: 'runs', maximum: 10, used: 9 }], { runs: 1 }).allowed).toBe(true);
    expect(checkQuota([{ dimension: 'runs', maximum: 10, used: 9 }], { runs: 2 }).allowed).toBe(false);
    expect(checkQuota([], { unknown: 1 }).allowed).toBe(false);
  });
});
