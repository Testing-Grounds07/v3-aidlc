# V3-AIDLC Repository Instructions

- Read `docs/architecture/` before changing a governed contract.
- Preserve the Python reference contracts while the TypeScript implementation is built.
- Keep provider-specific behavior behind adapters.
- Validate machine-consumed inputs and outputs at boundaries.
- Do not store raw credentials, prompts, or responses in state or telemetry.
- Run `pnpm verify` and the Python test suite before closing implementation work.
- Preserve unrelated user changes and record material architecture deviations as ADRs.
