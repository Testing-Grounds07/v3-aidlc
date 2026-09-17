# Implementation Milestone 5: Git Isolation and Change Proposals

**Status:** Complete
**Date:** 2026-09-17

## Objective

Give each bounded implementation job a real Git branch and worktree, then prepare a review-ready
proposal tied to its exact base, head revision, changed files, and verification evidence.

## Implemented

- safe Git invocation through argument arrays rather than shell commands;
- strict `v3/<name>` branch validation;
- exact base-revision resolution before worktree creation;
- worktree containment beneath a separate configured workspace root;
- real branch and worktree creation and inspection;
- branch/session identity checks before reuse;
- revision-bound change proposals with committed-change enforcement;
- sorted changed-file inventories and Git diff summaries;
- mandatory verification-evidence references;
- digest-protected proposal content;
- deterministic overlapping-file conflict reporting;
- durable PostgreSQL worktree sessions and change proposals;
- a durable `change-proposal.prepared` lifecycle event.

## Acceptance criteria

Milestone 5 closes when:

1. A Work Package can receive its own real branch and worktree at an exact base revision.
2. Unsafe branch names and workspace escapes fail before mutation.
3. The framework can detect branch drift and dirty worktrees.
4. A proposal cannot be prepared without a committed change and verification evidence.
5. Proposal identity is bound to its base revision, head revision, files, and evidence.
6. File overlap across proposals is explicit before integration.
7. Worktree and proposal records survive a PostgreSQL round trip.
8. Hosted PostgreSQL and the complete TypeScript/Python verification gates pass.

## Verification

GitHub Actions run
[`35183628900`](https://github.com/Testing-Grounds07/v3-aidlc/actions/runs/35183628900)
passed the complete hosted gate, including real Git worktree fixtures, the PostgreSQL migration and
six integration tests, all TypeScript checks and builds, and all 191 Python tests.
