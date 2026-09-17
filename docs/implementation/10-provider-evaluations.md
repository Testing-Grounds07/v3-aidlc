# Implementation Milestone 10: Provider Evaluations

**Status:** In progress
**Date:** 2026-09-17

## Objective

Compare AI runners on the same governed work, with the same context and independent scoring, then
use enough comparable evidence to improve routing without hard-coding assumptions about a vendor.

## Implemented

- versioned evaluation cases tied to exact context revisions;
- weighted rubrics with per-dimension minimums;
- independent evaluator enforcement;
- required evidence for candidates and every rubric score;
- hard-requirement checks that weighted averages cannot hide;
- digest-bound evaluation results;
- provider benchmarks segmented by task kind;
- minimum sample requirements before benchmark-based routing;
- posture-aware routing for speed, balanced value, or assurance;
- deterministic tie breaking;
- comparable-profile regression detection for pass rate, quality, and latency;
- durable PostgreSQL evaluation results and provider benchmarks;
- deterministic tests that require no live provider calls or credentials.

## Acceptance criteria

Milestone 10 closes when:

1. Candidates are compared against the same case version and context revision.
2. The evaluator is independent from the candidate producer.
3. Every score cites evidence and hard requirements cannot be averaged away.
4. Routing uses only eligible provider profiles with enough comparable samples.
5. Fast, balanced, and assured postures make explicit, deterministic tradeoffs.
6. Regression comparisons require the same profile and task kind.
7. Evaluation results and benchmarks survive a PostgreSQL round trip.
8. Hosted PostgreSQL and the complete TypeScript/Python verification gates pass.
