import json
import tempfile
import unittest
from pathlib import Path

from v3_aidlc.bootstrap import PROJECT_ID, bootstrap
from v3_aidlc.state_kernel import StateKernel, StatePaths


class StateKernelTest(unittest.TestCase):
    def test_bootstrap_creates_separate_canonical_state_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_path = bootstrap(root)
            paths = StatePaths(root, PROJECT_ID)

            self.assertTrue(paths.database.is_file())
            self.assertTrue(snapshot_path.is_file())
            self.assertEqual(snapshot_path, paths.exports_dir / "project-state.json")

            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["stateAuthority"], "state.db")
            self.assertFalse(snapshot["snapshotAuthority"])
            self.assertEqual(snapshot["project"]["id"], PROJECT_ID)
            self.assertIn(
                "V3.1-ARCH-01", {entity["id"] for entity in snapshot["entities"]}
            )
            self.assertEqual(len(snapshot["decisions"]), 4)

    def test_bootstrap_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bootstrap(root)
            bootstrap(root)
            kernel = StateKernel(StatePaths(root, PROJECT_ID))
            snapshot = kernel.snapshot()

            self.assertEqual(len(snapshot["events"]), 2)
            self.assertEqual(len(snapshot["decisions"]), 4)


if __name__ == "__main__":
    unittest.main()

