# Implementation Milestone 9: Process Health Analytics

**Status:** In progress
**Date:** 2026-09-17

## Objective

Show whether the delivery process is becoming faster and more reliable without rewarding raw
activity, hiding small samples, or mixing unlike kinds of work.

## Implemented

- first-pass yield, median cycle time, repair rate, decision wait, and blocked-time share;
- segmentation by route, mode, and posture;
- explicit reporting windows and accepted-work boundaries;
- median-based duration measures that resist extreme outliers;
- minimum sample requirements that produce `inconclusive` instead of fake trends;
- healthy, watch, unhealthy, and inconclusive states with plain explanations;
- recommendations tied to observed repair, decision, and blocker patterns;
- a process-health API endpoint;
- durable PostgreSQL health reports with their dimensions, samples, and recommendations;
- deterministic analytics, HTTP, and PostgreSQL tests.

## Acceptance criteria

Milestone 9 closes when:

1. Health measures focus on outcomes, rework, waiting, and verification rather than message or
   agent counts.
2. Unlike route, mode, or posture populations can be segmented before comparison.
3. Small samples are labeled inconclusive.
4. Cycle time uses accepted closure and does not treat unfinished work as completed.
5. Recommendations identify a concrete process response rather than a generic score.
6. Reports preserve their reporting window and sample size.
7. Reports survive a PostgreSQL round trip and are available through the API.
8. Hosted PostgreSQL and the complete TypeScript/Python verification gates pass.
