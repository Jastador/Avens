from __future__ import annotations

import unittest

from core.tts_segments import (
    ResumableSpeechPlan,
    estimate_resume_offset,
    find_chunk_span,
)


class TtsProgressTests(
    unittest.TestCase
):
    def test_chunk_span_is_found(
        self,
    ):
        text = (
            "First phrase. "
            "Second generated phrase."
        )

        result = find_chunk_span(
            text,
            "Second generated phrase.",
        )

        self.assertEqual(
            result,
            (
                text.index("Second"),
                len(text),
            ),
        )

    def test_chunk_search_respects_start_offset(
        self,
    ):
        text = "repeat this and repeat this"

        second_repeat = text.rindex(
            "repeat this"
        )

        result = find_chunk_span(
            text,
            "repeat this",
            start_offset=second_repeat,
        )

        self.assertEqual(
            result[0],
            second_repeat,
        )

    def test_chunk_search_is_case_insensitive(
        self,
    ):
        text = "Offline Models Run Locally."

        result = find_chunk_span(
            text,
            "offline models",
        )

        self.assertEqual(
            result,
            (
                0,
                len("Offline Models"),
            ),
        )

    def test_missing_chunk_uses_safe_fallback(
        self,
    ):
        text = "Original segment text."

        result = find_chunk_span(
            text,
            "normalised text",
            start_offset=4,
        )

        self.assertEqual(
            result[0],
            4,
        )
        self.assertLessEqual(
            result[1],
            len(text),
        )

    def test_zero_progress_resumes_at_chunk_start(
        self,
    ):
        text = "one two three four"

        result = estimate_resume_offset(
            text,
            chunk_start=0,
            chunk_end=len(text),
            elapsed_seconds=0.0,
            duration_seconds=4.0,
        )

        self.assertEqual(
            result,
            0,
        )

    def test_half_progress_skips_spoken_words(
        self,
    ):
        text = "one two three four six eight"

        result = estimate_resume_offset(
            text,
            chunk_start=0,
            chunk_end=len(text),
            elapsed_seconds=3.0,
            duration_seconds=6.0,
            replay_words=1,
        )

        self.assertEqual(
            text[result:],
            "three four six eight",
        )

    def test_replay_words_can_be_disabled(
        self,
    ):
        text = "one two three four"

        result = estimate_resume_offset(
            text,
            chunk_start=0,
            chunk_end=len(text),
            elapsed_seconds=2.0,
            duration_seconds=4.0,
            replay_words=0,
        )

        self.assertEqual(
            text[result:],
            "three four",
        )

    def test_progress_is_clamped(
        self,
    ):
        text = "one two three"

        result = estimate_resume_offset(
            text,
            chunk_start=0,
            chunk_end=len(text),
            elapsed_seconds=50.0,
            duration_seconds=3.0,
            replay_words=0,
        )

        self.assertEqual(
            result,
            len(text),
        )

    def test_remaining_text_starts_inside_current_segment(
        self,
    ):
        plan = ResumableSpeechPlan(
            segments=(
                "One two three four.",
                "Later sentence.",
            )
        )

        offset = plan.current_segment.index(
            "three"
        )

        self.assertEqual(
            plan.remaining_text_from_offset(
                offset
            ),
            "three four. Later sentence.",
        )

    def test_end_offset_skips_current_segment(
        self,
    ):
        plan = ResumableSpeechPlan(
            segments=(
                "Current sentence.",
                "Next sentence.",
            )
        )

        self.assertEqual(
            plan.remaining_text_from_offset(
                len(
                    plan.current_segment
                )
            ),
            "Next sentence.",
        )

    def test_completed_plan_has_no_remaining_text(
        self,
    ):
        plan = ResumableSpeechPlan(
            segments=(
                "Only sentence.",
            )
        )

        plan.mark_current_complete()

        self.assertEqual(
            plan.remaining_text_from_offset(
                0
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()