import copy
import unittest
from pathlib import Path

from v3_aidlc.conversational_gateway import (
    ActivationDecision,
    GatewayError,
    decide_activation,
    load_protocol,
    validate_envelope,
    validate_protocol,
    validate_relay,
    validate_transcript,
)


ROOT = Path(__file__).parents[1]


def envelope(kind, sender, recipient, payload, message_id="MSG-1", **extra):
    return {
        "schemaVersion": "0.1",
        "messageId": message_id,
        "conversationId": "CONV-1",
        "kind": kind,
        "sender": sender,
        "recipient": recipient,
        "createdAt": "2026-09-16T00:00:00Z",
        "payload": payload,
        **extra,
    }


class ConversationalGatewayTest(unittest.TestCase):
    def test_protocol_matches_executable_contract(self):
        protocol = load_protocol(ROOT / "protocols" / "conversational-gateway.json")
        validate_protocol(protocol)

    def test_simple_question_stays_conversational(self):
        result = decide_activation({"multiStep": False})
        self.assertEqual(result.decision, ActivationDecision.STAY_CONVERSATIONAL)

    def test_durable_multistep_work_starts_managed_intake(self):
        result = decide_activation(
            {"multiStep": True, "createsDurableArtifact": True}
        )
        self.assertEqual(result.decision, ActivationDecision.START_MANAGED_INTAKE)

    def test_existing_project_attaches_without_new_project(self):
        result = decide_activation({"existingProjectRef": "PRJ-V3-AIDLC"})
        self.assertEqual(result.decision, ActivationDecision.ATTACH_EXISTING_PROJECT)

    def test_ambiguous_project_identity_requires_clarification(self):
        result = decide_activation(
            {"existingProjectRef": "PRJ-ONE", "projectIdentityAmbiguous": True}
        )
        self.assertEqual(
            result.decision, ActivationDecision.CLARIFY_PROJECT_IDENTITY
        )

    def test_direction_is_enforced(self):
        invalid = envelope(
            "decision_needed",
            "liaison",
            "user",
            {"question": "Choose?", "options": [], "impact": "Changes timing."},
        )
        with self.assertRaisesRegex(GatewayError, "invalid sender"):
            validate_envelope(invalid)

    def test_intake_preserves_verbatim_request(self):
        source = envelope(
            "user_request",
            "user",
            "liaison",
            {"verbatimRequest": "Build the reporting app."},
        )
        relay = envelope(
            "intake_proposal",
            "liaison",
            "project_lead",
            {
                "verbatimRequest": "Build the reporting app.",
                "requestedOutcome": "A usable reporting app",
                "constraints": [],
                "assumptions": [],
            },
            message_id="MSG-2",
            correlationId="MSG-1",
        )
        validate_relay(source, relay)
        altered = copy.deepcopy(relay)
        altered["payload"]["verbatimRequest"] = "Build any app."
        with self.assertRaisesRegex(GatewayError, "verbatim request"):
            validate_relay(source, altered)

    def test_liaison_cannot_claim_canonical_decision(self):
        invalid = envelope(
            "decision_submission",
            "liaison",
            "project_lead",
            {
                "selectedOption": "A",
                "verbatimResponse": "Use A",
                "decisionId": "DEC-9999",
            },
        )
        with self.assertRaisesRegex(GatewayError, "canonical fields"):
            validate_envelope(invalid)

    def test_decision_relay_preserves_option_identity(self):
        source = envelope(
            "decision_needed",
            "project_lead",
            "liaison",
            {
                "question": "Release strategy?",
                "impact": "Changes exposure.",
                "options": [
                    {"id": "gradual", "label": "Canary"},
                    {"id": "immediate", "label": "All at once"},
                ],
            },
        )
        payload = {
            "headline": "Choose how broadly to release this",
            "explanation": "Testing is complete, and two safe paths remain.",
            "impact": "The choice changes how quickly everyone receives it.",
            "actionNeeded": "Choose the gradual or immediate release.",
            "question": "Which release approach should we use?",
            "options": [
                {"id": "gradual", "label": "Gradual", "tradeoff": "Slower, with easier rollback."},
                {"id": "immediate", "label": "Immediate", "tradeoff": "Faster, with wider exposure."},
            ],
        }
        relay = envelope(
            "decision_request",
            "liaison",
            "user",
            payload,
            message_id="MSG-2",
            correlationId="MSG-1",
        )
        validate_relay(source, relay)
        reversed_relay = copy.deepcopy(relay)
        reversed_relay["payload"]["options"].reverse()
        with self.assertRaisesRegex(GatewayError, "option IDs and order"):
            validate_relay(source, reversed_relay)

    def test_decision_request_uses_plain_language_and_options(self):
        valid = envelope(
            "decision_request",
            "liaison",
            "user",
            {
                "headline": "Choose how broadly to release this",
                "explanation": "Testing is complete, and two safe release paths remain.",
                "impact": "The choice changes how quickly all users receive it.",
                "actionNeeded": "Choose the gradual or immediate release.",
                "question": "Which release approach should we use?",
                "options": [
                    {"id": "gradual", "label": "Gradual", "tradeoff": "Slower, with easier rollback."},
                    {"id": "immediate", "label": "Immediate", "tradeoff": "Faster, with wider exposure."}
                ],
                "recommendationSupported": True,
                "recommendation": "Use the gradual release because rollback is easier."
            },
        )
        validate_envelope(valid)

    def test_internal_ids_are_kept_out_of_primary_user_message(self):
        invalid = envelope(
            "progress_update",
            "liaison",
            "user",
            {
                "headline": "V3.1-ARCH-05 is running",
                "explanation": "The work is underway.",
                "impact": "No impact yet.",
                "actionNeeded": "Nothing right now."
            },
        )
        with self.assertRaisesRegex(GatewayError, "Internal IDs"):
            validate_envelope(invalid)

    def test_framework_jargon_is_kept_out_of_primary_user_message(self):
        invalid = envelope(
            "progress_update",
            "liaison",
            "user",
            {
                "headline": "The work package is running",
                "explanation": "The bolt is underway.",
                "impact": "No impact yet.",
                "actionNeeded": "Nothing right now."
            },
        )
        with self.assertRaisesRegex(GatewayError, "jargon"):
            validate_envelope(invalid)

    def test_transcript_correlations_reference_earlier_messages(self):
        first = envelope(
            "user_request", "user", "liaison", {"verbatimRequest": "Build it."}
        )
        second = envelope(
            "intake_proposal",
            "liaison",
            "project_lead",
            {
                "verbatimRequest": "Build it.",
                "requestedOutcome": "A working result",
                "constraints": [],
                "assumptions": [],
            },
            message_id="MSG-2",
            correlationId="MSG-1",
        )
        validate_transcript([first, second])
        with self.assertRaisesRegex(GatewayError, "earlier message"):
            validate_transcript([second, first])


if __name__ == "__main__":
    unittest.main()
