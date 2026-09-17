# Implementation Milestone 6: GitHub and CI Evidence

**Status:** In progress
**Date:** 2026-09-17

## Objective

Publish an already prepared change to GitHub without losing its verified identity, then turn
hosted CI checks into formal evidence for the exact pull-request revision.

## Implemented

- an injectable GitHub client boundary that keeps API details outside project-domain code;
- strict `owner/repository` validation;
- branch publication with exact remote-revision confirmation;
- pull-request creation only when its head matches the verified proposal revision;
- normalized pull-request snapshots;
- hosted check collection tied to the exact head revision;
- digest-bound CI evidence without raw API payload persistence;
- explicit passed, failed, pending, missing, cancelled, timed-out, neutral, and skipped handling;
- CI gates that fail closed on missing or stale results;
- durable GitHub pull-request records and proposal publication state;
- a durable `pull-request.opened` lifecycle event;
- fake-client contract tests requiring no credentials or external writes.

## Acceptance criteria

Milestone 6 closes when:

1. A prepared proposal can be published and opened as a pull request through an adapter boundary.
2. Remote branch or pull-request revision drift prevents publication from being accepted.
3. CI checks become stable evidence records tied to the exact head revision.
4. Pending or missing required checks remain inconclusive rather than passing.
5. Failed, cancelled, or timed-out required checks are non-promotable.
6. Pull-request identity survives a PostgreSQL round trip without storing credentials or raw API
   responses.
7. Hosted PostgreSQL and the complete TypeScript/Python verification gates pass.
