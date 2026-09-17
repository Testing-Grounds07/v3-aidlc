# Implementation Milestone 11: Organizations and Teams

**Status:** Complete
**Date:** 2026-09-17

## Objective

Support multiple organizations and teams without allowing project data, authority, reviews, or
capacity to leak across tenant boundaries.

## Implemented

- organizations, teams, memberships, project assignments, and organization quotas;
- organization roles for owners, administrators, members, and auditors;
- team roles for leads, contributors, reviewers, and viewers;
- explicit permission grants with fail-closed defaults;
- project access limited to matching organization and team scope;
- invited, active, suspended, removed, and expiring memberships;
- independent-review enforcement across producer groups;
- inherited policy controls that retain every non-waivable control and the stricter maximum;
- unknown and exhausted quota dimensions that fail closed;
- transactional validation that teams belong to the assigned organization;
- optimistic quota consumption to prevent concurrent overuse;
- durable PostgreSQL organization, team, membership, assignment, and quota records;
- authorization, isolation, policy, quota, and PostgreSQL tests.

## Acceptance criteria

Milestone 11 closes when:

1. Every shared project can be assigned to one organization and team.
2. Active scoped membership is required for project permissions.
3. Cross-organization and cross-team access fails closed.
4. Suspension, removal, or expiry removes new authority immediately.
5. Reviewer independence remains enforceable in team settings.
6. Project policy cannot weaken organization hard controls or maximums.
7. Unknown, exhausted, or concurrently consumed quota cannot be overbooked.
8. Organization records survive a PostgreSQL round trip.
9. Hosted PostgreSQL and the complete TypeScript/Python verification gates pass.

## Verification

GitHub Actions run
[`35185733432`](https://github.com/Testing-Grounds07/v3-aidlc/actions/runs/35185733432)
passed the complete hosted gate, including tenant-isolation and quota tests, all eleven migrations,
all twelve PostgreSQL integration tests, 59 additional TypeScript tests, every build, and all 191
Python reference-contract tests.
