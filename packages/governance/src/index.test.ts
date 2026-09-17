import { describe, expect, it } from 'vitest';
import { GovernanceError, delegationAuthorizes, revokeDelegation, submitDecision, validateDecisionRequest, type StandingDelegation } from './index.js';

const request = validateDecisionRequest({
  id: 'DR-1', projectId: 'PRJ-1', actionId: 'ACTION-1', headline: 'Choose where to release',
  explanation: 'The change is ready, but releasing it affects real users.', impact: 'Your choice controls who receives the change.',
  actionNeeded: 'Choose one release option.', question: 'Where should this be released?',
  options: [
    { id: 'staging', label: 'Staging only', tradeoff: 'Safer, but real users will not receive it yet.' },
    { id: 'production', label: 'Production', tradeoff: 'Reaches users now and carries more risk.' },
  ],
  recommendedOptionId: 'staging', unaffectedWork: 'Documentation can continue while this waits.', requestedAt: new Date('2026-09-17T00:00:00Z'),
});

describe('human decisions', () => {
  it('preserves a valid bounded choice and the user’s exact words', () => {
    expect(submitDecision(request, {
      id: 'DEC-1', requestId: 'DR-1', projectId: 'PRJ-1', selectedOptionId: 'staging',
      userWords: 'Use staging for now.', submittedAt: new Date(),
    })).toMatchObject({ selectedOptionId: 'staging', userWords: 'Use staging for now.' });
  });

  it('rejects invented choices and framework jargon in primary text', () => {
    expect(() => submitDecision(request, {
      id: 'DEC-1', requestId: 'DR-1', projectId: 'PRJ-1', selectedOptionId: 'invented', userWords: 'Something else', submittedAt: new Date(),
    })).toThrow(GovernanceError);
    expect(() => validateDecisionRequest({ ...request, explanation: 'The work package needs a policy predicate.' })).toThrow('plain language');
  });
});

describe('standing delegations', () => {
  const delegation: StandingDelegation = {
    id: 'DEL-1', projectId: 'PRJ-1', grantedBy: 'user-1', actionTypes: ['deploy'], targets: ['staging'],
    requiredEvidence: ['EVID-CI'], policyVersion: '1.0.0', userWords: 'Deploy to staging after CI passes.',
    grantedAt: new Date('2026-09-17T00:00:00Z'), expiresAt: new Date('2026-09-18T00:00:00Z'),
  };

  it('authorizes only its exact action, target, evidence, project, and time window', () => {
    expect(delegationAuthorizes(delegation, {
      projectId: 'PRJ-1', actionType: 'deploy', target: 'staging', evidenceIds: ['EVID-CI'], at: new Date('2026-09-17T12:00:00Z'),
    })).toBe(true);
    expect(delegationAuthorizes(delegation, {
      projectId: 'PRJ-1', actionType: 'deploy', target: 'production', evidenceIds: ['EVID-CI'], at: new Date('2026-09-17T12:00:00Z'),
    })).toBe(false);
  });

  it('makes revocation immediately fail authorization', () => {
    const revoked = revokeDelegation(delegation, { at: new Date('2026-09-17T12:00:00Z'), userWords: 'Stop automatic staging releases.' });
    expect(delegationAuthorizes(revoked, {
      projectId: 'PRJ-1', actionType: 'deploy', target: 'staging', evidenceIds: ['EVID-CI'], at: new Date('2026-09-17T12:01:00Z'),
    })).toBe(false);
  });
});
