from __future__ import annotations

import unittest

from core.tts_segments import (
    ResumableSpeechPlan,
    split_response_segments,
)


class TtsSegmentTests(
    unittest.TestCase
):
    def test_empty_text_returns_no_segments(
        self,
    ):
        self.assertEqual(
            split_response_segments("   "),
            (),
        )

    def test_sentences_become_separate_segments(
        self,
    ):
        self.assertEqual(
            split_response_segments(
                "First sentence. "
                "Second sentence! "
                "Third sentence?"
            ),
            (
                "First sentence.",
                "Second sentence!",
                "Third sentence?",
            ),
        )

    def test_whitespace_is_normalised(
        self,
    ):
        self.assertEqual(
            split_response_segments(
                "First line.\n\n"
                "Second   line."
            ),
            (
                "First line.",
                "Second line.",
            ),
        )

    def test_titles_and_decimals_do_not_split_early(
        self,
    ):
        self.assertEqual(
            split_response_segments(
                "Dr. Rao measured 3.14 volts. "
                "The result was stable."
            ),
            (
                "Dr. Rao measured 3.14 volts.",
                "The result was stable.",
            ),
        )

    def test_closing_quote_stays_with_sentence(
        self,
    ):
        self.assertEqual(
            split_response_segments(
                'He said "Continue." '
                "Then he left."
            ),
            (
                'He said "Continue."',
                "Then he left.",
            ),
        )

    def test_long_text_respects_maximum_size(
        self,
    ):
        text = (
            "This is the first useful clause, "
            "this is the second useful clause, "
            "this is the third useful clause, "
            "and this is the final useful clause."
        )

        segments = split_response_segments(
            text,
            max_characters=55,
        )

        self.assertGreater(
            len(segments),
            1,
        )
        self.assertTrue(
            all(
                len(segment) <= 55
                for segment in segments
            )
        )
        self.assertEqual(
            " ".join(segments),
            text,
        )

    def test_too_small_maximum_is_rejected(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            split_response_segments(
                "Some text.",
                max_characters=20,
            )

    def test_plan_starts_at_first_segment(
        self,
    ):
        plan = (
            ResumableSpeechPlan.from_text(
                "One. Two. Three."
            )
        )

        self.assertFalse(
            plan.is_complete
        )
        self.assertEqual(
            plan.current_segment,
            "One.",
        )
        self.assertEqual(
            plan.remaining_text,
            "One. Two. Three.",
        )
        self.assertEqual(
            plan.completed_segments,
            (),
        )

    def test_completed_segment_moves_plan_forward(
        self,
    ):
        plan = (
            ResumableSpeechPlan.from_text(
                "One. Two. Three."
            )
        )

        plan.mark_current_complete()

        self.assertEqual(
            plan.current_segment,
            "Two.",
        )
        self.assertEqual(
            plan.completed_segments,
            ("One.",),
        )
        self.assertEqual(
            plan.remaining_segments,
            (
                "Two.",
                "Three.",
            ),
        )

    def test_uncompleted_segment_remains_available(
        self,
    ):
        plan = (
            ResumableSpeechPlan.from_text(
                "One. Two."
            )
        )

        self.assertEqual(
            plan.current_segment,
            "One.",
        )
        self.assertEqual(
            plan.remaining_text,
            "One. Two.",
        )

    def test_plan_reports_completion(
        self,
    ):
        plan = (
            ResumableSpeechPlan.from_text(
                "Only one."
            )
        )

        plan.mark_current_complete()

        self.assertTrue(
            plan.is_complete
        )
        self.assertIsNone(
            plan.current_segment
        )
        self.assertEqual(
            plan.remaining_segments,
            (),
        )
        self.assertEqual(
            plan.remaining_text,
            "",
        )

    def test_completed_plan_cannot_advance_again(
        self,
    ):
        plan = (
            ResumableSpeechPlan.from_text(
                "Only one."
            )
        )
        plan.mark_current_complete()

        with self.assertRaises(
            RuntimeError
        ):
            plan.mark_current_complete()


if __name__ == "__main__":
    unittest.main()