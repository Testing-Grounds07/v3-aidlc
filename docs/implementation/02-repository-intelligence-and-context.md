# Implementation Milestone 2: Repository Intelligence and Context

**Status:** In progress  
**Date:** 2026-09-17

## Objective

Produce a bounded, reproducible investigation grounded in the exact Git repository revision while
excluding secret-like paths and preserving the result as content-addressed evidence.

## Implemented

- safe Git inspection through argument-array process execution;
- exact root, branch, head revision, worktree cleanliness, tracked-file, and instruction discovery;
- path-containment, binary-content, per-file-size, and sensitive-path controls;
- deterministic task-to-file ranking with explicit context budgets;
- structured investigations covering relevant files, repository patterns, tests, unknowns, risks,
  exclusions, and total compiled bytes;
- content-addressed investigation artifacts;
- PostgreSQL repository registration and investigation references;
- durable `investigation.completed` events;
- fixture-based repository and context tests;
- hosted PostgreSQL persistence coverage.

## Acceptance criteria

Milestone 2 closes when:

1. A Git repository can be registered at an exact revision.
2. Repository instructions, relevant source, tests, and configuration can be discovered safely.
3. Context selection is deterministic and remains inside declared file and byte limits.
4. Sensitive paths, binary files, oversized files, and repository escapes are excluded or rejected.
5. A structured investigation is stored as a content-addressed artifact and referenced from
   PostgreSQL with a durable event.
6. The hosted migration, database tests, complete TypeScript gate, and Python reference suite pass.
