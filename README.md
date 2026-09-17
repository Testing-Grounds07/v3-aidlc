# V3-AIDLC

V3-AIDLC is an adaptive, evidence-driven control plane for AI-assisted and agentic software development.

It coordinates persistent project intent, adaptive lifecycle routes, parallel workstreams, stages, executable modes, bounded delivery cycles, independent review, deterministic verification, and human governance.

## Current status

The V3.1 architecture baseline and implementation Milestones 0–4 are complete. Milestone 5 is active.

- Completed packages: `V3.1-ARCH-01` through `V3.1-ARCH-14`
- Completed implementation: Milestone 0 repository foundation and hosted PostgreSQL verification
- Completed implementation: Milestone 1 governed domain records, transitions, events, and PostgreSQL reload
- Completed implementation: Milestone 2 repository intelligence, bounded context, and persisted investigations
- Completed implementation: Milestone 3 provider-neutral execution, capability negotiation, and normalized Agent Runs
- Completed implementation: Milestone 4 controlled orchestration, verification, independent review, and bounded repair
- Current work: Milestone 5 real Git isolation and review-ready change proposals
- Architecture specifications: `docs/architecture/`
- Governed Routes, Modes, policies, protocols, Checks, Gates, and Context Recipes live in their respective top-level directories.
- Managed project ID: `PRJ-V3-AIDLC`
- Live project state: stored outside this repository

## Runtime profiles

The architecture defines four standard operating profiles in `runtime-profiles/`:

- `local` for one-person development, trials, and prototypes;
- `team` for shared internal development;
- `hosted` for a persistent private service;
- `production` for fully governed, user-facing or business-critical operation.

## Repository and state separation

This repository contains the framework's source, specifications, schemas, migrations, playbooks, and tests. Live project state is stored in a separate configured state root.

`state.db` is authoritative. `project-state.json` is a generated, readable snapshot and must not be edited as an independent source of truth.

## Bootstrap commands

```bash
python3 -m v3_aidlc.bootstrap --state-root /path/to/v3-state
python3 -m v3_aidlc.snapshot --state-root /path/to/v3-state --project-id PRJ-V3-AIDLC
```

Run tests with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## TypeScript implementation

Requirements: Node.js 22 or newer, pnpm 11.19, and Docker or another PostgreSQL 17 instance.

```bash
cp .env.example .env
docker compose up -d postgres
pnpm install --frozen-lockfile
pnpm db:generate
pnpm db:migrate
pnpm verify
```

Run the initial shells with:

```bash
pnpm --filter @v3/cli dev -- doctor
pnpm --filter @v3/api dev
pnpm --filter @v3/web dev
```
