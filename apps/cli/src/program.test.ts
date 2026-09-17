import { describe, expect, it } from 'vitest';
import { createProgram } from './program.js';

describe('CLI shell', () => {
  it('runs the doctor command', async () => {
    const messages: string[] = [];
    await createProgram((message) => messages.push(message)).parseAsync(['node', 'harness', 'doctor']);
    expect(JSON.parse(messages[0] ?? '{}')).toEqual({ service: 'cli', status: 'ok', version: '0.1.0' });
  });
});
