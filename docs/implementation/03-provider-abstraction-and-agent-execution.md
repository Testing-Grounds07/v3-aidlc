# Implementation Milestone 3: Provider Abstraction and Agent Execution

**Status:** In progress  
**Date:** 2026-09-17

## Objective

Execute the same bounded Agent Run through different providers without changing project-domain or
orchestration contracts, while failing closed on capability, authorization, or output mismatch.

## Implemented

- provider-neutral Agent Run requests and normalized results;
- point-in-time capability profiles;
- exact role, capability, tool, host, size, sensitivity, structured-output, side-effect, and
  authorization negotiation;
- deterministic least-privilege provider selection;
- Codex and Claude adapters sharing one governed boundary;
- injectable transports so contract tests need no live provider or credentials;
- schema validation for provider output;
- completion-criterion and evidence enforcement;
- malformed-output and blocked-dispatch handling;
- normalized Agent Run persistence without copying raw provider payloads into canonical state;
- durable Agent Run completion/failure events.

## Acceptance criteria

Milestone 3 closes when:

1. The same role request executes through Codex and Claude adapters unchanged.
2. Missing capabilities, insufficient clearance, blocked authorization, and unsupported effects
   prevent dispatch.
3. Provider selection is deterministic and chooses the narrowest sufficient runner.
4. Malformed or incomplete provider output fails schema and evidence checks.
5. Canonical persistence contains stable normalized results and provider-result references, not raw
   provider objects or credentials.
6. Hosted PostgreSQL and complete TypeScript/Python verification pass.
