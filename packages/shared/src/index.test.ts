import { describe, expect, it } from 'vitest';
import { FRAMEWORK_NAME, healthReport } from './index.js';

describe('shared foundation', () => {
  it('creates a stable health report', () => {
    expect(healthReport('api')).toEqual({ service: 'api', status: 'ok', version: '0.1.0' });
    expect(FRAMEWORK_NAME).toBe('V3-AIDLC');
  });
});
