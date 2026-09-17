export type OrganizationRole = 'owner' | 'admin' | 'member' | 'auditor';
export type TeamRole = 'lead' | 'contributor' | 'reviewer' | 'viewer';
export type Permission =
  | 'organization:administer'
  | 'project:view'
  | 'project:plan'
  | 'work:execute'
  | 'work:review'
  | 'decision:approve'
  | 'delegation:grant'
  | 'report:view';

export interface Membership {
  readonly id: string;
  readonly organizationId: string;
  readonly teamId?: string;
  readonly principalId: string;
  readonly organizationRole: OrganizationRole;
  readonly teamRole?: TeamRole;
  readonly status: 'invited' | 'active' | 'suspended' | 'removed';
  readonly expiresAt?: Date;
}

export interface ProjectAssignment {
  readonly projectId: string;
  readonly organizationId: string;
  readonly teamId: string;
}

const organizationPermissions: Readonly<Record<OrganizationRole, readonly Permission[]>> = {
  owner: ['organization:administer', 'project:view', 'project:plan', 'work:execute', 'work:review', 'decision:approve', 'delegation:grant', 'report:view'],
  admin: ['organization:administer', 'project:view', 'project:plan', 'work:execute', 'work:review', 'delegation:grant', 'report:view'],
  member: ['project:view', 'report:view'],
  auditor: ['project:view', 'report:view'],
};
const teamPermissions: Readonly<Record<TeamRole, readonly Permission[]>> = {
  lead: ['project:view', 'project:plan', 'work:execute', 'work:review', 'decision:approve', 'report:view'],
  contributor: ['project:view', 'work:execute', 'report:view'],
  reviewer: ['project:view', 'work:review', 'report:view'],
  viewer: ['project:view'],
};

export interface AuthorizationResult {
  readonly allowed: boolean;
  readonly reason: string;
  readonly membershipId?: string;
}

export function authorizeProjectAction(input: {
  readonly principalId: string;
  readonly project: ProjectAssignment;
  readonly permission: Permission;
  readonly memberships: readonly Membership[];
  readonly now: Date;
  readonly producerIndependenceGroup?: string;
  readonly reviewerIndependenceGroup?: string;
}): AuthorizationResult {
  if (input.permission === 'work:review' && input.producerIndependenceGroup !== undefined && input.producerIndependenceGroup === input.reviewerIndependenceGroup) {
    return { allowed: false, reason: 'The reviewer must be independent from the work producer.' };
  }
  const applicable = input.memberships.filter((membership) =>
    membership.principalId === input.principalId
    && membership.organizationId === input.project.organizationId
    && membership.status === 'active'
    && (membership.expiresAt === undefined || membership.expiresAt > input.now)
    && (membership.teamId === undefined || membership.teamId === input.project.teamId));
  for (const membership of applicable) {
    const permissions = new Set<Permission>(organizationPermissions[membership.organizationRole]);
    for (const permission of membership.teamRole === undefined ? [] : teamPermissions[membership.teamRole]) permissions.add(permission);
    if (permissions.has(input.permission)) return { allowed: true, reason: 'An active scoped membership grants this action.', membershipId: membership.id };
  }
  return { allowed: false, reason: 'No active membership grants this action for this project.' };
}

export interface OrganizationPolicy {
  readonly id: string;
  readonly version: string;
  readonly nonWaivableControls: readonly string[];
  readonly maximums: Readonly<Record<string, number>>;
}

export function inheritPolicy(organization: OrganizationPolicy, project: OrganizationPolicy): OrganizationPolicy {
  const maximums: Record<string, number> = { ...organization.maximums };
  for (const [name, value] of Object.entries(project.maximums)) maximums[name] = Math.min(maximums[name] ?? value, value);
  return {
    id: `${organization.id}+${project.id}`,
    version: `${organization.version}+${project.version}`,
    nonWaivableControls: [...new Set([...organization.nonWaivableControls, ...project.nonWaivableControls])].sort(),
    maximums,
  };
}

export interface QuotaGrant { readonly dimension: string; readonly maximum: number; readonly used: number }
export function checkQuota(grants: readonly QuotaGrant[], costs: Readonly<Record<string, number>>): AuthorizationResult {
  for (const [dimension, cost] of Object.entries(costs)) {
    const grant = grants.find((item) => item.dimension === dimension);
    if (grant === undefined) return { allowed: false, reason: `No organization quota is configured for ${dimension}.` };
    if (cost < 0 || grant.used + cost > grant.maximum) return { allowed: false, reason: `The organization quota for ${dimension} would be exceeded.` };
  }
  return { allowed: true, reason: 'The requested capacity is within organization quotas.' };
}
