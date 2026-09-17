# Implementation Milestone 1: Domain and Persistence

**Status:** Complete  
**Date:** 2026-09-17

## Objective

Implement the minimum production-shaped domain and PostgreSQL persistence path required to
create, govern, reload, and resume a project without relying on conversation history.

## Scope

- Project, Requirement, Acceptance Criterion, Plan, Work Package, and Lifecycle Event records;
- V3.1 adaptive Work Package context for Intent, Route, Workstream, Unit, Bolt, Stage, Mode,
  Posture, Risk Profile, expected outcomes, and promotion target;
- deterministic Work Package transition guards;
- append-oriented transition events with aggregate versions;
- transactional PostgreSQL creation and retrieval of the complete project graph;
- optimistic version checks for state transitions;
- unit tests for domain invariants and invalid transitions;
- PostgreSQL integration tests for create, reload, transition, and event persistence.

## Acceptance criteria

Milestone 1 closes when:

1. Project → Requirement → Acceptance Criterion → Plan → Work Package can be created in one
   transaction.
2. Invalid Work Package transitions fail before persistence.
3. Meaningful creation and transition actions emit durable Lifecycle Events.
4. The complete graph reloads from PostgreSQL with its adaptive lifecycle context intact.
5. Concurrent transition writes are rejected by an optimistic version check.
6. Formatting, lint, type checking, unit tests, builds, migration deployment, PostgreSQL
   integration tests, and the Python reference-contract suite pass in hosted verification.

## Deliberate boundary

The richer hash-linked Event Envelope, evidence store, leases, findings, learning, and recovery
planner remain preserved in the Python reference contracts. They move into the TypeScript product
runtime in later orchestration and verification milestones rather than being partially duplicated
inside Milestone 1.

## Verification

GitHub Actions run
[`35181846124`](https://github.com/Testing-Grounds07/v3-aidlc/actions/runs/35181846124)
passed the full gate, including both PostgreSQL round-trip tests, migration deployment, all
TypeScript checks and builds, and all 191 Python reference-contract tests.
