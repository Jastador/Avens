from __future__ import annotations

import unittest

from core.barge_intent import (
    BargeInDecision,
    BargeInIntent,
    classify_barge_in,
    normalise_barge_text,
)


class BargeIntentTests(unittest.TestCase):
    def test_normalise_barge_text(self):
        self.assertEqual(
            normalise_barge_text(
                "  Wait... WHAT do you mean? "
            ),
            "wait what do you mean",
        )

    def test_empty_transcript_is_unclear(self):
        decision = classify_barge_in("   ")

        self.assertEqual(
            decision.intent,
            BargeInIntent.UNCLEAR,
        )
        self.assertTrue(decision.should_resume)

    def test_avens_direct_address_is_directed(self):
        decision = classify_barge_in(
            "Avens, wait a second."
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.DIRECTED,
        )
        self.assertEqual(
            decision.reason,
            "direct_address",
        )

    def test_whisper_evans_alias_is_directed(self):
        decision = classify_barge_in(
            "Hey Evans, stop."
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.DIRECTED,
        )

    def test_question_is_directed(self):
        decision = classify_barge_in(
            "What do you mean by local data?"
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.DIRECTED,
        )
        self.assertEqual(
            decision.reason,
            "question",
        )

    def test_command_is_directed(self):
        decision = classify_barge_in(
            "Open Discord."
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.DIRECTED,
        )
        self.assertEqual(
            decision.reason,
            "command",
        )

    def test_correction_is_directed(self):
        decision = classify_barge_in(
            "No, that is not correct."
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.DIRECTED,
        )
        self.assertEqual(
            decision.reason,
            "correction",
        )

    def test_hmm_is_acknowledgement(self):
        decision = classify_barge_in("Hmm.")

        self.assertEqual(
            decision.intent,
            BargeInIntent.ACKNOWLEDGEMENT,
        )
        self.assertTrue(decision.should_resume)

    def test_got_it_is_acknowledgement(self):
        decision = classify_barge_in("Got it.")

        self.assertEqual(
            decision.intent,
            BargeInIntent.ACKNOWLEDGEMENT,
        )

    def test_side_talk_is_background(self):
        decision = classify_barge_in(
            "Haan mummy, aa raha hoon."
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.BACKGROUND,
        )
        self.assertTrue(decision.should_resume)

    def test_matching_spoken_text_is_echo(self):
        decision = classify_barge_in(
            (
                "Offline language models run "
                "on the local computer."
            ),
            spoken_text=(
                "Offline language models run "
                "on the local computer."
            ),
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.ECHO,
        )
        self.assertTrue(decision.should_resume)

    def test_partial_long_spoken_text_is_echo(self):
        decision = classify_barge_in(
            (
                "language models run locally "
                "without internet access"
            ),
            spoken_text=(
                "Offline language models run locally "
                "without internet access and keep "
                "private data on the computer."
            ),
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.ECHO,
        )

    def test_short_matching_phrase_is_not_echo(self):
        decision = classify_barge_in(
            "local model",
            spoken_text=(
                "A local model runs directly "
                "on your computer."
            ),
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.UNCLEAR,
        )

    def test_unrelated_statement_is_unclear(self):
        decision = classify_barge_in(
            "The package arrived this afternoon."
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.UNCLEAR,
        )
        self.assertTrue(decision.should_resume)

    def test_directed_decision_does_not_resume(self):
        decision = BargeInDecision(
            intent=BargeInIntent.DIRECTED,
            reason="test",
            confidence=1.0,
        )

        self.assertTrue(decision.is_directed)
        self.assertFalse(decision.should_resume)

    def test_confirmation_question_is_directed(
        self,
    ):
        decision = classify_barge_in(
            (
                "So basically offline is the "
                "safest method, right?"
            )
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.DIRECTED,
        )
        self.assertEqual(
            decision.reason,
            "question",
        )

    def test_confirmation_question_without_punctuation_is_directed(
        self,
    ):
        decision = classify_barge_in(
            (
                "So basically offline is the "
                "safest method right"
            )
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.DIRECTED,
        )

    def test_side_talk_question_remains_background(
        self,
    ):
        decision = classify_barge_in(
            "Haan mummy, aa raha hoon?"
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.BACKGROUND,
        )

    def test_go_to_sleep_is_directed_command(
        self,
    ):
        decision = classify_barge_in(
            "Go to sleep."
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.DIRECTED,
        )
        self.assertEqual(
            decision.reason,
            "command",
        )

    def test_sleep_now_is_directed_command(
        self,
    ):
        decision = classify_barge_in(
            "Sleep now."
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.DIRECTED,
        )
        self.assertEqual(
            decision.reason,
            "command",
        )

    def test_sleep_topic_is_not_command(
        self,
    ):
        decision = classify_barge_in(
            "Sleep quality affects memory."
        )

        self.assertEqual(
            decision.intent,
            BargeInIntent.UNCLEAR,
        )

if __name__ == "__main__":
    unittest.main()