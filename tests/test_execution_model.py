import json
import unittest
from pathlib import Path

from v3_aidlc.execution_model import (
    InvalidTransition,
    ProjectLeadState,
    WorkPackageState,
    require_project_lead_transition,
    require_work_package_transition,
)


class ExecutionModelTest(unittest.TestCase):
    def test_json_schema_enums_match_executable_states(self) -> None:
        schema_path = Path(__file__).parents[1] / "schemas" / "execution-state.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            set(schema["properties"]["projectLeadState"]["enum"]),
            {state.value for state in ProjectLeadState},
        )
        self.assertEqual(
            set(schema["properties"]["workPackageState"]["enum"]),
            {state.value for state in WorkPackageState},
        )

    def test_project_lead_can_wake_reconcile_select_and_dispatch(self) -> None:
        path = [
            ProjectLeadState.SLEEPING,
            ProjectLeadState.RECONCILING,
            ProjectLeadState.SELECTING,
            ProjectLeadState.DISPATCHING,
            ProjectLeadState.WAITING,
            ProjectLeadState.EVALUATING,
            ProjectLeadState.SELECTING,
        ]
        for current, requested in zip(path, path[1:]):
            require_project_lead_transition(current, requested)

    def test_project_lead_cannot_skip_reconciliation(self) -> None:
        with self.assertRaisesRegex(InvalidTransition, "allowed"):
            require_project_lead_transition(
                ProjectLeadState.SLEEPING, ProjectLeadState.DISPATCHING
            )

    def test_work_package_happy_path(self) -> None:
        path = [
            WorkPackageState.PROPOSED,
            WorkPackageState.PLANNED,
            WorkPackageState.ELIGIBLE,
            WorkPackageState.LEASED,
            WorkPackageState.RUNNING,
            WorkPackageState.VERIFYING,
            WorkPackageState.REVIEWING,
            WorkPackageState.ACCEPTED,
            WorkPackageState.CLOSED,
        ]
        for current, requested in zip(path, path[1:]):
            require_work_package_transition(current, requested)

    def test_repair_must_reenter_through_a_lease(self) -> None:
        require_work_package_transition(
            WorkPackageState.REVIEWING, WorkPackageState.REPAIR_REQUIRED
        )
        require_work_package_transition(
            WorkPackageState.REPAIR_REQUIRED, WorkPackageState.LEASED
        )
        with self.assertRaises(InvalidTransition):
            require_work_package_transition(
                WorkPackageState.REPAIR_REQUIRED, WorkPackageState.ACCEPTED
            )

    def test_closed_work_package_is_terminal(self) -> None:
        with self.assertRaisesRegex(InvalidTransition, "allowed: none"):
            require_work_package_transition(
                WorkPackageState.CLOSED, WorkPackageState.RUNNING
            )


if __name__ == "__main__":
    unittest.main()
