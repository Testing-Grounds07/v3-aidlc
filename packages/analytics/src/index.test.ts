import { describe, expect, it } from 'vitest';
import { analyzeProcessHealth, type WorkObservation } from './index.js';

const day = 86_400_000;
const observation = (id: string, repairs: number, decisionWaitMs = 0, blockedMs = 0): WorkObservation => ({
  workPackageId: id, route: 'production', mode: 'feature', posture: 'balanced',
  startedAt: new Date('2026-09-10T00:00:00Z'), closedAt: new Date(Date.parse('2026-09-10T00:00:00Z') + day),
  repairAttempts: repairs, verificationAttempts: repairs + 1, decisionWaitMs, blockedMs, accepted: true,
});

describe('process health analytics', () => {
  it('marks small samples inconclusive instead of pretending they are a trend', () => {
    const report = analyzeProcessHealth({ projectId: 'PRJ-1', observations: [observation('WP-1', 0)], windowStart: new Date('2026-09-01'), windowEnd: new Date('2026-10-01') });
    expect(report.metrics.firstPassYield.status).toBe('inconclusive');
  });

  it('segments comparable work and recommends action for repeated repair', () => {
    const report = analyzeProcessHealth({
      projectId: 'PRJ-1', observations: [observation('WP-1', 3), observation('WP-2', 2), observation('WP-3', 4), { ...observation('WP-4', 0), mode: 'prototype' }],
      windowStart: new Date('2026-09-01'), windowEnd: new Date('2026-10-01'), dimensions: { mode: 'feature' },
    });
    expect(report.metrics.repairRate).toMatchObject({ sampleSize: 3, status: 'unhealthy', value: 3 });
    expect(report.recommendations).toContain('Review recurring findings before increasing parallel work.');
  });

  it('rejects an invalid reporting window', () => {
    expect(() => analyzeProcessHealth({ projectId: 'PRJ-1', observations: [], windowStart: new Date('2026-10-01'), windowEnd: new Date('2026-09-01') })).toThrow('must end after');
  });
});
