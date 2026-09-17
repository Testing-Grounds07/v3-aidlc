# Implementation Milestone 0: Repository Foundation

**Status:** Implemented; database runtime verification pending  
**Date:** 2026-09-17

## Objective

Establish the buildable and testable TypeScript repository foundation specified by the V3 master plan without beginning orchestration or provider behavior.

## Implemented

- pnpm TypeScript monorepo with strict shared compiler settings;
- React and Vite web shell;
- Express API shell with a minimal health endpoint;
- Node CLI shell with a `harness doctor` command;
- shared, configuration, domain-placeholder, and database packages;
- Zod environment validation;
- ESLint, Prettier, Vitest, and production builds;
- PostgreSQL Prisma schema and initial migration;
- local PostgreSQL Compose definition;
- GitHub Actions verification with a real PostgreSQL service;
- joint TypeScript and Python verification;
- ADR-0015 preserving the Python contracts as a reference layer.

## Verification

Passed locally:

- dependency installation and frozen-lockfile reinstall;
- all workspace resolution;
- formatting;
- lint;
- TypeScript type checking;
- five Vitest tests;
- all workspace production builds;
- Prisma client generation;
- Prisma schema validation;
- migration SQL generation;
- 191 Python reference-contract tests.

Pending in this execution environment:

- connect to PostgreSQL and apply the migration.

The workspace has no Docker, PostgreSQL server, container alternative, or permission to install a system PostgreSQL package. CI and `compose.yml` contain the required real-database verification path. Milestone 0 remains open until one of those paths produces migration evidence.

## Deferred to Milestone 1

- governed domain entities;
- lifecycle transition guards;
- event persistence;
- repository implementations for the domain chain;
- PostgreSQL reload/resume verification.
