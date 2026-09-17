# ADR-0015: TypeScript implementation beside the Python reference contracts

**Status:** Accepted  
**Date:** 2026-09-17

## Context

The V3 master specification selects TypeScript and Node.js for the product implementation. The V3.1 architecture work produced useful executable Python reference contracts and 191 tests.

## Decision

Build the product as a pnpm TypeScript monorepo in the same repository while retaining the Python code as an executable conformance and architecture reference during implementation.

## Consequences

- Product surfaces and future orchestration use TypeScript.
- Existing Python contracts remain verified and available for comparison.
- CI runs both suites until contract parity permits a separate retirement decision.
- New behavior is not implemented twice unless needed for conformance.
