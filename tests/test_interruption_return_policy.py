from __future__ import annotations

import unittest

from core.interruption_return_policy import (
    InterruptionReturnAction,
    decide_interruption_return,
    normalise_interruption_text,
)


class InterruptionReturnPolicyTests(
    unittest.TestCase
):
    def test_normalises_text(self):
        self.assertEqual(
            normalise_interruption_text(
                "  Wait... WHAT does that mean? "
            ),
            "wait what does that mean",
        )

    def test_question_preserves_response(self):
        decision = decide_interruption_return(
            "What does local data mean?",
            classification_reason="question",
        )

        self.assertEqual(
            decision.action,
            InterruptionReturnAction.PRESERVE,
        )
        self.assertTrue(
            decision.should_preserve
        )

    def test_how_question_preserves_response(self):
        decision = decide_interruption_return(
            "How does that work?"
        )

        self.assertTrue(
            decision.should_preserve
        )

    def test_correction_preserves_response(self):
        decision = decide_interruption_return(
            "No, that is not correct.",
            classification_reason="correction",
        )

        self.assertTrue(
            decision.should_preserve
        )
        self.assertEqual(
            decision.reason,
            "correction",
        )

    def test_wait_clarification_preserves_response(self):
        decision = decide_interruption_return(
            "Wait, what do you mean?"
        )

        self.assertTrue(
            decision.should_preserve
        )

    def test_direct_address_question_preserves_response(self):
        decision = decide_interruption_return(
            "Avens, what do you mean by that?",
            classification_reason="direct_address",
        )

        self.assertTrue(
            decision.should_preserve
        )

    def test_command_replaces_response(self):
        decision = decide_interruption_return(
            "Open Discord.",
            classification_reason="command",
        )

        self.assertEqual(
            decision.action,
            InterruptionReturnAction.REPLACE,
        )
        self.assertFalse(
            decision.should_preserve
        )

    def test_direct_address_command_replaces_response(self):
        decision = decide_interruption_return(
            "Avens, open Discord.",
            classification_reason="direct_address",
        )

        self.assertEqual(
            decision.action,
            InterruptionReturnAction.REPLACE,
        )
        self.assertEqual(
            decision.reason,
            "explicit_command",
        )

    def test_stop_replaces_response(self):
        decision = decide_interruption_return(
            "Stop."
        )

        self.assertEqual(
            decision.action,
            InterruptionReturnAction.REPLACE,
        )

    def test_new_statement_replaces_response(self):
        decision = decide_interruption_return(
            "The package arrived today."
        )

        self.assertEqual(
            decision.action,
            InterruptionReturnAction.REPLACE,
        )

    def test_empty_transcript_replaces_response(self):
        decision = decide_interruption_return(
            "   "
        )

        self.assertEqual(
            decision.action,
            InterruptionReturnAction.REPLACE,
        )
        self.assertEqual(
            decision.reason,
            "empty_transcript",
        )


if __name__ == "__main__":
    unittest.main()