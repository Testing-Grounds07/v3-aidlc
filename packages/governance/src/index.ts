import { z } from 'zod';

export class GovernanceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'GovernanceError';
  }
}

const optionSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  tradeoff: z.string().min(1),
});

const decisionRequestSchema = z.object({
  id: z.string().min(1),
  projectId: z.string().min(1),
  actionId: z.string().min(1),
  headline: z.string().min(1),
  explanation: z.string().min(1),
  impact: z.string().min(1),
  actionNeeded: z.string().min(1),
  question: z.string().min(1),
  options: z.array(optionSchema).min(2).max(4),
  recommendedOptionId: z.string().min(1).optional(),
  unaffectedWork: z.string().min(1),
  requestedAt: z.coerce.date(),
});

export type DecisionRequest = z.infer<typeof decisionRequestSchema>;

const internalTerms = /\b(work package|bolt|route instance|posture|canonical state|policy predicate)\b/i;

export function validateDecisionRequest(value: unknown): DecisionRequest {
  const parsed = decisionRequestSchema.safeParse(value);
  if (!parsed.success) throw new GovernanceError('Decision request failed schema validation');
  const ids = new Set(parsed.data.options.map(({ id }) => id));
  if (ids.size !== parsed.data.options.length) throw new GovernanceError('Decision option IDs must be unique');
  if (parsed.data.recommendedOptionId !== undefined && !ids.has(parsed.data.recommendedOptionId)) {
    throw new GovernanceError('Recommended option must identify a presented choice');
  }
  for (const field of [parsed.data.headline, parsed.data.explanation, parsed.data.impact, parsed.data.actionNeeded]) {
    if (internalTerms.test(field)) throw new GovernanceError('Primary user-facing text must use plain language');
  }
  return parsed.data;
}

export interface DecisionSubmission {
  readonly id: string;
  readonly requestId: string;
  readonly projectId: string;
  readonly selectedOptionId: string;
  readonly userWords: string;
  readonly submittedAt: Date;
}

export function submitDecision(request: DecisionRequest, input: DecisionSubmission): DecisionSubmission {
  if (input.requestId !== request.id || input.projectId !== request.projectId) throw new GovernanceError('Decision does not match its request');
  if (!request.options.some(({ id }) => id === input.selectedOptionId)) throw new GovernanceError('Decision must select a presented option');
  if (input.userWords.trim().length === 0) throw new GovernanceError('The user’s exact words are required');
  return { ...input, userWords: input.userWords.trim() };
}

export interface StandingDelegation {
  readonly id: string;
  readonly projectId: string;
  readonly grantedBy: string;
  readonly actionTypes: readonly string[];
  readonly targets: readonly string[];
  readonly requiredEvidence: readonly string[];
  readonly policyVersion: string;
  readonly userWords: string;
  readonly grantedAt: Date;
  readonly expiresAt?: Date;
  readonly revokedAt?: Date;
  readonly revocationWords?: string;
}

export function delegationAuthorizes(
  delegation: StandingDelegation,
  input: { readonly projectId: string; readonly actionType: string; readonly target: string; readonly evidenceIds: readonly string[]; readonly at: Date },
): boolean {
  return delegation.projectId === input.projectId
    && delegation.revokedAt === undefined
    && (delegation.expiresAt === undefined || delegation.expiresAt > input.at)
    && delegation.actionTypes.includes(input.actionType)
    && delegation.targets.includes(input.target)
    && delegation.requiredEvidence.every((id) => input.evidenceIds.includes(id));
}

export function revokeDelegation(delegation: StandingDelegation, input: { readonly at: Date; readonly userWords: string }): StandingDelegation {
  if (delegation.revokedAt !== undefined) throw new GovernanceError('Delegation is already revoked');
  if (input.userWords.trim().length === 0) throw new GovernanceError('The user’s exact revocation words are required');
  return { ...delegation, revokedAt: input.at, revocationWords: input.userWords.trim() };
}

export interface DecisionService {
  listPending(projectId: string): Promise<readonly DecisionRequest[]>;
  decide(input: DecisionSubmission): Promise<DecisionSubmission>;
  revoke(input: { readonly projectId: string; readonly delegationId: string; readonly userWords: string }): Promise<StandingDelegation>;
}

export class InMemoryDecisionService implements DecisionService {
  private readonly requests = new Map<string, DecisionRequest>();
  private readonly decisions = new Map<string, DecisionSubmission>();
  private readonly delegations = new Map<string, StandingDelegation>();

  addRequest(request: DecisionRequest): void { this.requests.set(request.id, validateDecisionRequest(request)); }
  addDelegation(delegation: StandingDelegation): void { this.delegations.set(delegation.id, delegation); }

  async listPending(projectId: string): Promise<readonly DecisionRequest[]> {
    return [...this.requests.values()].filter((request) => request.projectId === projectId && ![...this.decisions.values()].some(({ requestId }) => requestId === request.id));
  }

  async decide(input: DecisionSubmission): Promise<DecisionSubmission> {
    const request = this.requests.get(input.requestId);
    if (request === undefined) throw new GovernanceError('Unknown decision request');
    if ([...this.decisions.values()].some(({ requestId }) => requestId === input.requestId)) throw new GovernanceError('Decision request is already resolved');
    const result = submitDecision(request, input);
    this.decisions.set(result.id, result);
    return result;
  }

  async revoke(input: { readonly projectId: string; readonly delegationId: string; readonly userWords: string }): Promise<StandingDelegation> {
    const delegation = this.delegations.get(input.delegationId);
    if (delegation === undefined || delegation.projectId !== input.projectId) throw new GovernanceError('Unknown delegation');
    const revoked = revokeDelegation(delegation, { at: new Date(), userWords: input.userWords });
    this.delegations.set(revoked.id, revoked);
    return revoked;
  }
}
