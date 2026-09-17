# Implementation Milestone 7: Human Approval and Liaison

**Status:** Complete
**Date:** 2026-09-17

## Objective

Pause only the affected work when a decision belongs to a person, explain the choice in everyday
language, preserve exactly what the user said, and make any continuing authority narrow,
time-bounded, evidence-dependent, and immediately revocable.

## Implemented

- decision requests with headline, explanation, impact, action needed, and unaffected work;
- two to four concrete options with tradeoffs and an optional valid recommendation;
- plain-language enforcement for primary user-facing fields;
- exact option-ID validation so the liaison cannot invent a choice;
- preservation of the user’s exact decision and revocation words;
- standing delegations scoped to project, action, target, evidence, policy version, and time;
- immediate authorization failure after revocation;
- API endpoints to list pending choices, submit a choice, and revoke a delegation;
- duplicate-decision and unknown-delegation rejection;
- durable decision requests, decisions, delegations, revocations, and lifecycle events;
- contract and HTTP tests for the human approval flow.

## Acceptance criteria

Milestone 7 closes when:

1. A user receives one focused question in everyday language with bounded, meaningful choices.
2. Internal framework terms stay out of the primary explanation.
3. A submission can select only an option actually offered and preserves the user’s exact words.
4. Independent work is described separately rather than pausing the whole project.
5. Standing authority applies only to its exact project, action, target, evidence, and time window.
6. Revocation immediately prevents new use of that authority.
7. Decisions and delegations survive a PostgreSQL round trip with durable events.
8. Hosted PostgreSQL and the complete TypeScript/Python verification gates pass.

## Verification

GitHub Actions run
[`35184324200`](https://github.com/Testing-Grounds07/v3-aidlc/actions/runs/35184324200)
passed the complete hosted gate, including HTTP approval tests, governance contracts, the
PostgreSQL migration and eight integration tests, all builds, and all 191 Python tests.
