import copy
import unittest
from pathlib import Path

from v3_aidlc.lifecycle_contracts import (
    ContractError,
    load_contract,
    load_mode_library,
    select_modes,
    validate_route_contract,
)


ROOT = Path(__file__).parents[1]


class LifecycleContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mode_library = load_mode_library(sorted((ROOT / "modes").glob("*.json")))
        cls.production = load_contract(ROOT / "routes" / "production-ready.json")
        cls.feasibility = load_contract(ROOT / "routes" / "feasibility.json")

    def test_example_routes_validate(self) -> None:
        validate_route_contract(self.production, self.mode_library)
        validate_route_contract(self.feasibility, self.mode_library)

    def test_production_design_selects_ui_for_user_facing_work(self) -> None:
        result = select_modes(
            self.production,
            self.mode_library,
            stage="design",
            facts={"userFacing": True},
        )
        selected = {item.mode_id: item.requirement for item in result.selected}
        self.assertEqual(
            selected,
            {
                "MODE-ARCHITECTURE": "required",
                "MODE-UI-PROTOTYPE": "conditional",
                "MODE-INDEPENDENT-REVIEW": "required",
            },
        )
        self.assertIn("CTRL-NO-SELF-APPROVAL", result.inherited_controls)
        self.assertIn("CTRL-ACCESSIBILITY-BASELINE", result.inherited_controls)

    def test_non_user_facing_design_does_not_select_ui(self) -> None:
        result = select_modes(
            self.production,
            self.mode_library,
            stage="design",
            facts={"userFacing": False},
        )
        self.assertNotIn(
            "MODE-UI-PROTOTYPE", {item.mode_id for item in result.selected}
        )

    def test_feasibility_route_can_complete_without_hardening(self) -> None:
        result = select_modes(
            self.feasibility,
            self.mode_library,
            stage="discovery",
            facts={},
        )
        self.assertEqual(
            [item.mode_id for item in result.selected], ["MODE-INVESTIGATION"]
        )
        self.assertIn("not_viable", self.feasibility["completionOutcomes"])
        self.assertNotIn("MODE-HARDENING", {item.mode_id for item in result.selected})

    def test_optional_mode_requires_explicit_selection(self) -> None:
        without_optional = select_modes(
            self.feasibility,
            self.mode_library,
            stage="design",
            facts={"uncertaintyType": "technical"},
        )
        with_optional = select_modes(
            self.feasibility,
            self.mode_library,
            stage="design",
            facts={"uncertaintyType": "technical"},
            optional_mode_ids=["MODE-ARCHITECTURE"],
        )
        self.assertEqual(without_optional.selected, ())
        self.assertEqual(
            [item.mode_id for item in with_optional.selected], ["MODE-ARCHITECTURE"]
        )

    def test_unknown_mode_fails_closed(self) -> None:
        invalid = copy.deepcopy(self.production)
        invalid["stages"][0]["modeRules"][0]["modeId"] = "MODE-MISSING"
        with self.assertRaisesRegex(ContractError, "unknown mode"):
            validate_route_contract(invalid, self.mode_library)

    def test_conditional_mode_requires_a_condition(self) -> None:
        invalid = copy.deepcopy(self.production)
        del invalid["stages"][1]["modeRules"][1]["whenAll"]
        with self.assertRaisesRegex(ContractError, "requires whenAll"):
            validate_route_contract(invalid, self.mode_library)

    def test_route_cannot_request_unsupported_posture(self) -> None:
        with self.assertRaisesRegex(ContractError, "not allowed"):
            select_modes(
                self.feasibility,
                self.mode_library,
                stage="discovery",
                facts={},
                posture="assured",
            )


if __name__ == "__main__":
    unittest.main()

