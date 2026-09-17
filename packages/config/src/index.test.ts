import { describe, expect, it } from 'vitest';
import { readEnvironment } from './index.js';

describe('environment configuration', () => {
  it('validates and types settings', () => {
    expect(readEnvironment({ DATABASE_URL: 'postgresql://example', V3_API_PORT: '4200' })).toEqual({
      DATABASE_URL: 'postgresql://example',
      V3_API_PORT: 4200,
    });
  });

  it('rejects missing database configuration', () => {
    expect(() => readEnvironment({})).toThrow();
  });
});
