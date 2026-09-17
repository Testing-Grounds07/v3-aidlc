import { describe, expect, it } from 'vitest';
import { createProgram } from './program.js';

describe('CLI shell', () => {
  it('runs the doctor command', async () => {
    const messages: string[] = [];
    await createProgram((message) => messages.push(message)).parseAsync(['node', 'harness', 'doctor']);
    expect(JSON.parse(messages[0] ?? '{}')).toEqual({ service: 'cli', status: 'ok', version: '0.1.0' });
  });

  it('explains the controlled lifecycle in plain language', async () => {
    const messages: string[] = [];
    await createProgram((message) => messages.push(message)).parseAsync(['node', 'harness', 'lifecycle', 'explain']);
    expect(JSON.parse(messages[0] ?? '{}')).toMatchObject({ repairLimit: 3 });
  });

  it('explains a lifecycle state', async () => {
    const messages: string[] = [];
    await createProgram((message) => messages.push(message)).parseAsync([
      'node', 'harness', 'lifecycle', 'status', '--state', 'repair_required',
    ]);
    expect(JSON.parse(messages[0] ?? '{}')).toEqual({
      state: 'repair_required',
      explanation: 'A check or review found something that must be fixed.',
    });
  });
});
