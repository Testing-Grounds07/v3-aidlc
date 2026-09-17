import { describe, expect, it } from 'vitest';
import request from 'supertest';
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
});
