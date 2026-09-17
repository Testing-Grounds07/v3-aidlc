import { describe, expect, it } from 'vitest';
import { plainStatus, summarizeWork, type DashboardWorkItem } from './index.js';

const item = (status: string): DashboardWorkItem => ({
  id: status, title: status, workstream: 'Core', stage: 'Implementation', mode: 'Feature development',
  posture: 'Balanced', status, progress: 50, summary: 'Current work', lastUpdatedAt: new Date(),
});

describe('dashboard projection', () => {
  it('separates completed, active, waiting, and blocked work', () => {
    expect(summarizeWork(['closed', 'running', 'decision_required', 'blocked'].map(item))).toEqual({
      completed: 1, active: 1, waiting: 1, blocked: 1,
    });
  });

  it('translates internal states into familiar labels', () => {
    expect(plainStatus('repair_required')).toBe('Needs a fix');
    expect(plainStatus('unknown')).toBe('Status unavailable');
  });
});
