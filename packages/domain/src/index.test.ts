import { describe, expect, it } from 'vitest';

import {
  DomainValidationError,
  InvalidTransitionError,
  assertWorkPackageTransition,
  transitionWorkPackage,
  validateProjectGraph,
  type ProjectGraph,
  type WorkPackage,
} from './index.js';

const now = new Date('2026-09-17T00:00:00.000Z');

function workPackage(status: WorkPackage['status'] = 'planned'): WorkPackage {
  return {
    id: 'WP-1', projectId: 'PRJ-1', planId: 'PLAN-1', title: 'Implement persistence',
    objective: 'Persist and reload the graph', status, version: 1, intentIds: ['INT-1'],
    stage: 'implementation', posture: 'balanced', expectedOutcomeTypes: ['accepted_result'],
    createdAt: now, updatedAt: now,
  };
}

describe('work package lifecycle', () => {
  it('allows a governed transition and emits an attributable event', () => {
    const result = transitionWorkPackage(workPackage(), 'eligible', 'EVT-1', now);
    expect(result.workPackage.status).toBe('eligible');
    expect(result.workPackage.version).toBe(2);
    expect(result.event).toMatchObject({
      id: 'EVT-1', aggregateId: 'WP-1', aggregateVersion: 2,
      payload: { from: 'planned', to: 'eligible' },
    });
  });

  it('rejects skipping verification and review', () => {
    expect(() => assertWorkPackageTransition('running', 'accepted')).toThrow(InvalidTransitionError);
  });

  it('treats closed packages as terminal', () => {
    expect(() => assertWorkPackageTransition('closed', 'eligible')).toThrow('cannot transition from closed');
  });
});

describe('project graph invariants', () => {
  it('accepts a fully linked project graph', () => {
    const graph: ProjectGraph = {
      project: { id: 'PRJ-1', name: 'V3', description: 'Harness', status: 'active', version: 1, createdAt: now, updatedAt: now },
      requirements: [{
        id: 'REQ-1', projectId: 'PRJ-1', title: 'Persist state', description: 'Durable state',
        status: 'approved', version: 1, createdAt: now, updatedAt: now,
        acceptanceCriteria: [{ id: 'AC-1', requirementId: 'REQ-1', statement: 'State reloads', verificationMethod: 'integration test', createdAt: now, updatedAt: now }],
      }],
      plans: [{ id: 'PLAN-1', projectId: 'PRJ-1', title: 'Persistence', objective: 'Persist it', status: 'approved', version: 1, createdAt: now, updatedAt: now, workPackages: [workPackage()] }],
      events: [],
    };
    expect(() => validateProjectGraph(graph)).not.toThrow();
  });

  it('requires acceptance criteria for every requirement', () => {
    const graph = {
      project: { id: 'PRJ-1', name: 'V3', description: '', status: 'active', version: 1, createdAt: now, updatedAt: now },
      requirements: [{ id: 'REQ-1', projectId: 'PRJ-1', title: 'R', description: '', status: 'draft', version: 1, createdAt: now, updatedAt: now, acceptanceCriteria: [] }],
      plans: [], events: [],
    } satisfies ProjectGraph;
    expect(() => validateProjectGraph(graph)).toThrow(DomainValidationError);
  });
});
