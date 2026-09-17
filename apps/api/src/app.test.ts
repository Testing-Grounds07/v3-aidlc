import { describe, expect, it } from 'vitest';
import request from 'supertest';
import { InMemoryProcessHealthService } from '@v3/analytics';
import { InMemoryDashboardService } from '@v3/dashboard';
import { InMemoryDecisionService } from '@v3/governance';
import { createApp } from './app.js';

describe('API shell', () => {
  it('reports health without exposing internals', async () => {
    const response = await request(createApp()).get('/health').expect(200);
    expect(response.body).toEqual({ service: 'api', status: 'ok', version: '0.1.0' });
  });

  it('lists and records a bounded human decision', async () => {
    const decisions = new InMemoryDecisionService();
    decisions.addRequest({
      id: 'DR-1', projectId: 'PRJ-1', actionId: 'ACTION-1', headline: 'Choose a release target',
      explanation: 'The change is ready, but releasing it affects other people.', impact: 'Your choice controls who receives it.',
      actionNeeded: 'Choose one option.', question: 'Where should it be released?',
      options: [
        { id: 'staging', label: 'Staging', tradeoff: 'Safer but not public.' },
        { id: 'production', label: 'Production', tradeoff: 'Public with more risk.' },
      ],
      recommendedOptionId: 'staging', unaffectedWork: 'Documentation can continue.', requestedAt: new Date(),
    });
    const app = createApp({ decisions });
    expect((await request(app).get('/projects/PRJ-1/decisions').expect(200)).body.decisions).toHaveLength(1);
    const result = await request(app).post('/projects/PRJ-1/decisions/DR-1').send({
      id: 'DEC-1', selectedOptionId: 'staging', userWords: 'Use staging for now.',
    }).expect(201);
    expect(result.body).toMatchObject({ selectedOptionId: 'staging', userWords: 'Use staging for now.' });
    expect((await request(app).get('/projects/PRJ-1/decisions').expect(200)).body.decisions).toHaveLength(0);
  });

  it('rejects a choice that was not offered', async () => {
    const decisions = new InMemoryDecisionService();
    decisions.addRequest({
      id: 'DR-1', projectId: 'PRJ-1', actionId: 'ACTION-1', headline: 'Choose a release target',
      explanation: 'The change is ready, but releasing it affects other people.', impact: 'Your choice controls who receives it.',
      actionNeeded: 'Choose one option.', question: 'Where should it be released?',
      options: [{ id: 'stop', label: 'Stop', tradeoff: 'No release.' }, { id: 'staging', label: 'Staging', tradeoff: 'Internal only.' }],
      unaffectedWork: 'Other work can continue.', requestedAt: new Date(),
    });
    await request(createApp({ decisions })).post('/projects/PRJ-1/decisions/DR-1').send({
      id: 'DEC-1', selectedOptionId: 'production', userWords: 'Use production.',
    }).expect(400);
  });

  it('returns a plain project dashboard snapshot', async () => {
    const now = new Date('2026-09-17T00:00:00Z');
    const dashboard = new InMemoryDashboardService([{
      project: { id: 'PRJ-1', name: 'V3', outcome: 'Adaptive delivery', status: 'active' },
      summary: { completed: 1, active: 1, waiting: 0, blocked: 0 },
      work: [{ id: 'WP-1', title: 'Dashboard', workstream: 'Product', stage: 'Implementation', mode: 'Feature development', posture: 'Balanced', status: 'running', progress: 50, summary: 'Building the dashboard', lastUpdatedAt: now }],
      decisions: [], evidence: { passed: 4, failed: 0, inconclusive: 0, updatedAt: now },
    }]);
    const response = await request(createApp({ dashboard })).get('/projects/PRJ-1/dashboard').expect(200);
    expect(response.body).toMatchObject({ project: { name: 'V3' }, summary: { active: 1 }, evidence: { passed: 4 } });
  });

  it('returns the latest sample-aware process health report', async () => {
    const inconclusive = { value: null, unit: 'ratio' as const, sampleSize: 1, status: 'inconclusive' as const, explanation: 'Not enough work.' };
    const report = {
      projectId: 'PRJ-1', windowStart: new Date('2026-09-01'), windowEnd: new Date('2026-10-01'), dimensions: {},
      metrics: {
        firstPassYield: inconclusive,
        medianCycleTime: { ...inconclusive, unit: 'milliseconds' as const },
        repairRate: { ...inconclusive, unit: 'count' as const },
        medianDecisionWait: { ...inconclusive, unit: 'milliseconds' as const },
        blockedShare: inconclusive,
      },
      recommendations: ['Collect more data.'],
    };
    const response = await request(createApp({ processHealth: new InMemoryProcessHealthService([report]) }))
      .get('/projects/PRJ-1/process-health').expect(200);
    expect(response.body).toMatchObject({ projectId: 'PRJ-1', metrics: { firstPassYield: { status: 'inconclusive' } } });
  });
});
