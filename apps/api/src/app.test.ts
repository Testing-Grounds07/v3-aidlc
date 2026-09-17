import { describe, expect, it } from 'vitest';
import request from 'supertest';
import { createApp } from './app.js';

describe('API shell', () => {
  it('reports health without exposing internals', async () => {
    const response = await request(createApp()).get('/health').expect(200);
    expect(response.body).toEqual({ service: 'api', status: 'ok', version: '0.1.0' });
  });
});
