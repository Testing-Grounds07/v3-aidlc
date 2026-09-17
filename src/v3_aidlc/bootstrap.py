"""Initialize the V3-AIDLC project in a separate canonical state store."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .state_kernel import StateKernel, StatePaths


PROJECT_ID = "PRJ-V3-AIDLC"


def bootstrap(state_root: Path) -> Path:
    paths = StatePaths(state_root.resolve(), PROJECT_ID)
    kernel = StateKernel(paths)
    kernel.initialize_schema()
    kernel.upsert_project("V3-AIDLC", "active")

    entities = [
        (
            "INT-V3-01",
            "intent",
            "Create an adaptive AI-driven development control plane",
            "active",
            {
                "summary": (
                    "Manage different kinds of development work with appropriate "
                    "autonomy, speed, assurance, and plain-language user interaction."
                )
            },
        ),
        (
            "ROUTE-V3-01",
            "route-instance",
            "Production-ready framework route",
            "active",
            {"definition": "production-ready", "tailoringStatus": "bootstrap"},
        ),
        (
            "WS-ARCH-01",
            "workstream",
            "Core architecture",
            "active",
            {},
        ),
        (
            "UNIT-ARCH-01",
            "unit",
            "Adaptive lifecycle domain model",
            "active",
            {"currentStage": "design", "posture": "balanced"},
        ),
        (
            "MODE-ARCH-01",
            "mode",
            "Architecture mode",
            "active",
            {},
        ),
        (
            "BOLT-ARCH-01",
            "bolt",
            "Architecture foundation bolt",
            "active",
            {},
        ),
        (
            "V3.1-ARCH-01",
            "work-package",
            "Adaptive Lifecycle Domain Model",
            "in_progress",
            {
                "artifact": (
                    "docs/architecture/"
                    "V3.1-ARCH-01-adaptive-lifecycle-domain-model.md"
                ),
                "nextPackage": "V3.1-ARCH-02",
            },
        ),
    ]
    for entity in entities:
        kernel.upsert_entity(*entity)

    relationships = [
        ("ROUTE-V3-01", "realizes", "INT-V3-01"),
        ("WS-ARCH-01", "participates-in", "ROUTE-V3-01"),
        ("WS-ARCH-01", "serves", "INT-V3-01"),
        ("UNIT-ARCH-01", "belongs-to", "WS-ARCH-01"),
        ("UNIT-ARCH-01", "advances", "INT-V3-01"),
        ("MODE-ARCH-01", "active-for", "UNIT-ARCH-01"),
        ("BOLT-ARCH-01", "advances", "UNIT-ARCH-01"),
        ("V3.1-ARCH-01", "belongs-to", "BOLT-ARCH-01"),
    ]
    for relationship in relationships:
        kernel.relate(*relationship)

    decisions = [
        (
            "DEC-0001",
            "Name the framework repository v3-aidlc",
            "The user selected v3-aidlc as the authoritative framework repository name.",
        ),
        (
            "DEC-0002",
            "Keep live project state separate from the framework repository",
            (
                "The repository defines the framework; the external state store records "
                "the live managed-project history."
            ),
        ),
        (
            "DEC-0003",
            "Use state.db as the sole state authority",
            (
                "project-state.json is generated for readability and is not an "
                "independently editable source of truth."
            ),
        ),
        (
            "DEC-0004",
            "Require the conversational liaison to use layman's terms",
            (
                "Users should receive accurate explanations of outcomes, impacts, "
                "choices, required actions, and next steps without needing V3 terminology."
            ),
        ),
    ]
    for decision in decisions:
        kernel.record_decision(*decision)

    kernel.append_event(
        "EVT-0001",
        "project.created",
        "project",
        PROJECT_ID,
        {"bootstrap": True},
    )
    kernel.append_event(
        "EVT-0002",
        "work-package.started",
        "work-package",
        "V3.1-ARCH-01",
        {"stage": "design", "mode": "architecture", "posture": "balanced"},
    )

    binding = {
        "schemaVersion": "0.1",
        "projectId": PROJECT_ID,
        "repository": "Testing-Grounds07/v3-aidlc",
        "defaultBranch": "main",
        "frameworkVersion": "bootstrap",
        "stateAuthority": "state.db",
        "snapshotAuthority": False,
    }
    (paths.config_dir / "project-binding.json").write_text(
        json.dumps(binding, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return kernel.write_snapshot()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True, type=Path)
    args = parser.parse_args()
    print(bootstrap(args.state_root))


if __name__ == "__main__":
    main()

