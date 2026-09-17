"""Regenerate a readable snapshot from canonical V3-AIDLC state."""

from __future__ import annotations

import argparse
from pathlib import Path

from .state_kernel import StateKernel, StatePaths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    kernel = StateKernel(StatePaths(args.state_root.resolve(), args.project_id))
    print(kernel.write_snapshot())


if __name__ == "__main__":
    main()

