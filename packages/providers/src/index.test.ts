import { describe, expect, it } from 'vitest';

import {
  ClaudeAdapter,
  CodexAdapter,
  ProviderContractError,
  ProviderRegistry,
  type AgentRunRequest,
  type CapabilityProfile,
  type ProviderTransport,
} from './index.js';

const request: AgentRunRequest = {
  id: 'RUN-1', projectId: 'PRJ-1', workPackageId: 'WP-1', role: 'implementer',
  objective: 'Implement the bounded change', contextManifestId: 'CTX-1',
  contextDigest: 'a'.repeat(64), contextBytes: 1024, sensitivity: 'internal',
  requiredCapabilities: ['code-edit'], requiredTools: ['filesystem'], requiredNetworkHosts: [],
  structuredOutput: true, externalEffects: false, maxOutputBytes: 4096,
  completionCriteria: ['AC-1'], authorization: 'proceed', attempt: 1, idempotencyKey: 'idem-1',
};

function profile(adapterId: string, maxContextBytes = 8192): Omit<CapabilityProfile, 'provider'> {
  return {
    id: `PROFILE-${adapterId}`, adapterId, adapterVersion: '1.0.0', model: 'test-model',
    status: 'available', roles: ['implementer'], capabilities: ['code-edit'], tools: ['filesystem'],
    networkHosts: [], maxContextBytes, maxOutputBytes: 8192, maxSensitivity: 'internal',
    structuredOutput: true, externalEffects: false, idempotent: true,
  };
}

function transport(stdout: string): ProviderTransport {
  return {
    async invoke() {
      return {
        stdout,
        providerResultRef: 'provider-result://1',
        startedAt: new Date('2026-09-17T00:00:00Z'),
        finishedAt: new Date('2026-09-17T00:00:01Z'),
      };
    },
  };
}

const successfulOutput = JSON.stringify({
  status: 'completed', summary: 'Implemented', artifactIds: ['ART-1'], evidenceIds: ['EVD-1'],
  findingIds: [], satisfiedCriteria: ['AC-1'], usage: { inputTokens: 10, outputTokens: 20 },
});

describe('provider adapters', () => {
  it.each([
    ['Codex', new CodexAdapter(profile('codex'), transport(successfulOutput))],
    ['Claude', new ClaudeAdapter(profile('claude'), transport(successfulOutput))],
  ])('runs the same role through %s without changing the request contract', async (_name, adapter) => {
    await expect(adapter.run(request)).resolves.toMatchObject({
      runId: 'RUN-1', status: 'completed', satisfiedCriteria: ['AC-1'], evidenceIds: ['EVD-1'],
    });
  });

  it('rejects malformed provider output', async () => {
    const adapter = new CodexAdapter(profile('codex'), transport('not json'));
    await expect(adapter.run(request)).rejects.toThrow(ProviderContractError);
  });

  it('rejects unsupported or blocked dispatches before invocation', async () => {
    const adapter = new CodexAdapter(profile('codex'), transport(successfulOutput));
    await expect(adapter.run({ ...request, authorization: 'block' })).rejects.toThrow('authorization');
  });

  it('requires evidence for a completion claim', async () => {
    const output = JSON.stringify({ status: 'completed', summary: 'Done', satisfiedCriteria: ['AC-1'] });
    await expect(new ClaudeAdapter(profile('claude'), transport(output)).run(request)).rejects.toThrow('lacks criteria or evidence');
  });
});

describe('ProviderRegistry', () => {
  it('selects the narrowest sufficient runner deterministically', async () => {
    const registry = new ProviderRegistry();
    const large = new CodexAdapter(profile('codex-large', 16384), transport(successfulOutput));
    const narrow = new ClaudeAdapter(profile('claude-narrow', 4096), transport(successfulOutput));
    registry.register('codex-large', large);
    registry.register('claude-narrow', narrow);
    expect(await registry.select(request)).toBe(narrow);
  });
});
