import { createHash } from 'node:crypto';

import { z } from 'zod';

export type AgentRole = 'investigator' | 'planner' | 'implementer' | 'reviewer';
export type Sensitivity = 'public' | 'internal' | 'confidential' | 'restricted' | 'secret';

export interface CapabilityProfile {
  readonly id: string;
  readonly adapterId: string;
  readonly adapterVersion: string;
  readonly provider: 'codex' | 'claude';
  readonly model: string;
  readonly status: 'available' | 'degraded' | 'unavailable';
  readonly roles: readonly AgentRole[];
  readonly capabilities: readonly string[];
  readonly tools: readonly string[];
  readonly networkHosts: readonly string[];
  readonly maxContextBytes: number;
  readonly maxOutputBytes: number;
  readonly maxSensitivity: Sensitivity;
  readonly structuredOutput: boolean;
  readonly externalEffects: boolean;
  readonly idempotent: boolean;
}

export interface AgentRunRequest {
  readonly id: string;
  readonly projectId: string;
  readonly workPackageId: string;
  readonly role: AgentRole;
  readonly objective: string;
  readonly contextManifestId: string;
  readonly contextDigest: string;
  readonly contextBytes: number;
  readonly sensitivity: Sensitivity;
  readonly requiredCapabilities: readonly string[];
  readonly requiredTools: readonly string[];
  readonly requiredNetworkHosts: readonly string[];
  readonly structuredOutput: boolean;
  readonly externalEffects: boolean;
  readonly maxOutputBytes: number;
  readonly completionCriteria: readonly string[];
  readonly authorization: 'proceed' | 'proceed_with_record' | 'escalate' | 'block';
  readonly attempt: number;
  readonly idempotencyKey: string;
}

export interface AgentRunResult {
  readonly runId: string;
  readonly projectId: string;
  readonly workPackageId: string;
  readonly adapterId: string;
  readonly profileId: string;
  readonly requestDigest: string;
  readonly status: 'completed' | 'failed' | 'blocked' | 'cancelled';
  readonly summary: string;
  readonly artifactIds: readonly string[];
  readonly evidenceIds: readonly string[];
  readonly findingIds: readonly string[];
  readonly satisfiedCriteria: readonly string[];
  readonly usage: Readonly<{ inputTokens?: number; outputTokens?: number }>;
  readonly providerResultRef: string;
  readonly startedAt: Date;
  readonly finishedAt: Date;
}

export interface ProviderInvocation {
  readonly provider: 'codex' | 'claude';
  readonly model: string;
  readonly request: AgentRunRequest;
  readonly requestDigest: string;
}

export interface ProviderTransport {
  invoke(invocation: ProviderInvocation): Promise<{
    readonly stdout: string;
    readonly providerResultRef: string;
    readonly startedAt: Date;
    readonly finishedAt: Date;
  }>;
}

export interface AgentRunner {
  capabilityProfile(): Promise<CapabilityProfile>;
  run(request: AgentRunRequest): Promise<AgentRunResult>;
}

export class ProviderContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ProviderContractError';
  }
}

const outputSchema = z.object({
  status: z.enum(['completed', 'failed', 'blocked', 'cancelled']),
  summary: z.string().min(1),
  artifactIds: z.array(z.string()).default([]),
  evidenceIds: z.array(z.string()).default([]),
  findingIds: z.array(z.string()).default([]),
  satisfiedCriteria: z.array(z.string()).default([]),
  usage: z.object({ inputTokens: z.number().int().nonnegative().optional(), outputTokens: z.number().int().nonnegative().optional() }).default({}),
});

const sensitivityRank: Readonly<Record<Sensitivity, number>> = {
  public: 0,
  internal: 1,
  confidential: 2,
  restricted: 3,
  secret: 4,
};

function canonicalDigest(value: unknown): string {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex');
}

function missing(profile: CapabilityProfile, request: AgentRunRequest): string[] {
  const reasons: string[] = [];
  if (profile.status !== 'available') reasons.push(`profile is ${profile.status}`);
  if (!profile.roles.includes(request.role)) reasons.push(`role ${request.role} is unsupported`);
  for (const item of request.requiredCapabilities) if (!profile.capabilities.includes(item)) reasons.push(`missing capability ${item}`);
  for (const item of request.requiredTools) if (!profile.tools.includes(item)) reasons.push(`missing tool ${item}`);
  for (const item of request.requiredNetworkHosts) if (!profile.networkHosts.includes(item)) reasons.push(`missing network host ${item}`);
  if (request.contextBytes > profile.maxContextBytes) reasons.push('context exceeds runner limit');
  if (request.maxOutputBytes > profile.maxOutputBytes) reasons.push('output exceeds runner limit');
  if (sensitivityRank[request.sensitivity] > sensitivityRank[profile.maxSensitivity]) reasons.push('context exceeds runner sensitivity clearance');
  if (request.structuredOutput && !profile.structuredOutput) reasons.push('structured output is unsupported');
  if (request.externalEffects && !profile.externalEffects) reasons.push('external effects are unsupported');
  if (request.authorization === 'block' || request.authorization === 'escalate') reasons.push(`authorization is ${request.authorization}`);
  return reasons;
}

abstract class StructuredAdapter implements AgentRunner {
  constructor(
    private readonly profile: CapabilityProfile,
    private readonly transport: ProviderTransport,
  ) {}

  async capabilityProfile(): Promise<CapabilityProfile> {
    return this.profile;
  }

  async run(request: AgentRunRequest): Promise<AgentRunResult> {
    const reasons = missing(this.profile, request);
    if (reasons.length > 0) throw new ProviderContractError(reasons.join('; '));
    const requestDigest = canonicalDigest(request);
    const raw = await this.transport.invoke({
      provider: this.profile.provider,
      model: this.profile.model,
      request,
      requestDigest,
    });
    let parsedJson: unknown;
    try {
      parsedJson = JSON.parse(raw.stdout);
    } catch {
      throw new ProviderContractError('Provider returned malformed JSON');
    }
    const parsed = outputSchema.safeParse(parsedJson);
    if (!parsed.success) throw new ProviderContractError('Provider output failed schema validation');
    if (parsed.data.status === 'completed') {
      const unsatisfied = request.completionCriteria.filter(
        (criterion) => !parsed.data.satisfiedCriteria.includes(criterion),
      );
      if (unsatisfied.length > 0 || parsed.data.evidenceIds.length === 0) {
        throw new ProviderContractError('Completion claim lacks criteria or evidence');
      }
    } else if (parsed.data.satisfiedCriteria.length > 0) {
      throw new ProviderContractError('Non-completed result cannot claim satisfied criteria');
    }
    const usage: AgentRunResult['usage'] = {
      ...(parsed.data.usage.inputTokens === undefined
        ? {}
        : { inputTokens: parsed.data.usage.inputTokens }),
      ...(parsed.data.usage.outputTokens === undefined
        ? {}
        : { outputTokens: parsed.data.usage.outputTokens }),
    };
    return {
      runId: request.id,
      projectId: request.projectId,
      workPackageId: request.workPackageId,
      adapterId: this.profile.adapterId,
      profileId: this.profile.id,
      requestDigest,
      status: parsed.data.status,
      summary: parsed.data.summary,
      artifactIds: parsed.data.artifactIds,
      evidenceIds: parsed.data.evidenceIds,
      findingIds: parsed.data.findingIds,
      satisfiedCriteria: parsed.data.satisfiedCriteria,
      usage,
      providerResultRef: raw.providerResultRef,
      startedAt: raw.startedAt,
      finishedAt: raw.finishedAt,
    };
  }
}

export class CodexAdapter extends StructuredAdapter {
  constructor(profile: Omit<CapabilityProfile, 'provider'>, transport: ProviderTransport) {
    super({ ...profile, provider: 'codex' }, transport);
  }
}

export class ClaudeAdapter extends StructuredAdapter {
  constructor(profile: Omit<CapabilityProfile, 'provider'>, transport: ProviderTransport) {
    super({ ...profile, provider: 'claude' }, transport);
  }
}

export class ProviderRegistry {
  private readonly runners = new Map<string, AgentRunner>();

  register(adapterId: string, runner: AgentRunner): void {
    if (this.runners.has(adapterId)) throw new ProviderContractError(`Duplicate adapter ${adapterId}`);
    this.runners.set(adapterId, runner);
  }

  async select(request: AgentRunRequest): Promise<AgentRunner> {
    const eligible: { runner: AgentRunner; profile: CapabilityProfile }[] = [];
    const rejections: string[] = [];
    for (const [adapterId, runner] of this.runners) {
      const profile = await runner.capabilityProfile();
      const reasons = missing(profile, request);
      if (reasons.length === 0) eligible.push({ runner, profile });
      else rejections.push(`${adapterId}: ${reasons.join(', ')}`);
    }
    eligible.sort((left, right) => {
      const sensitivity = sensitivityRank[left.profile.maxSensitivity] - sensitivityRank[right.profile.maxSensitivity];
      if (sensitivity !== 0) return sensitivity;
      const context = left.profile.maxContextBytes - right.profile.maxContextBytes;
      if (context !== 0) return context;
      const output = left.profile.maxOutputBytes - right.profile.maxOutputBytes;
      if (output !== 0) return output;
      return left.profile.adapterId.localeCompare(right.profile.adapterId);
    });
    const selected = eligible[0];
    if (selected === undefined) throw new ProviderContractError(`No eligible provider. ${rejections.join(' | ')}`);
    return selected.runner;
  }
}
