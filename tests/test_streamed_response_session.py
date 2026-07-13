from __future__ import annotations

import unittest

from core.streamed_response_session import (
    StreamedResponseSession,
)


class StreamedResponseSessionTests(
    unittest.TestCase
):
    def test_new_session_starts_empty(
        self,
    ):
        session = StreamedResponseSession()

        self.assertEqual(
            session.completed_segments,
            (),
        )
        self.assertEqual(
            session.pending_segments,
            (),
        )
        self.assertIsNone(
            session.current_segment
        )
        self.assertFalse(
            session.generation_complete
        )
        self.assertFalse(
            session.interrupted
        )
        self.assertFalse(
            session.is_complete
        )

    def test_append_text_normalises_whitespace(
        self,
    ):
        session = StreamedResponseSession()

        appended = session.append_text(
            "  First   generated\nsegment.  "
        )

        self.assertTrue(appended)
        self.assertEqual(
            session.pending_segments,
            (
                "First generated segment.",
            ),
        )

    def test_empty_text_is_ignored(
        self,
    ):
        session = StreamedResponseSession()

        appended = session.append_text(
            "   \n "
        )

        self.assertFalse(appended)
        self.assertEqual(
            session.pending_segments,
            (),
        )

    def test_begin_next_segment_activates_first_pending_event(
        self,
    ):
        session = StreamedResponseSession()
        session.append_text("First.")
        session.append_text("Second.")

        segment = (
            session.begin_next_segment()
        )

        self.assertEqual(
            segment,
            "First.",
        )
        self.assertEqual(
            session.current_segment,
            "First.",
        )
        self.assertEqual(
            session.remaining_text,
            "First. Second.",
        )

    def test_completed_segment_advances_session(
        self,
    ):
        session = StreamedResponseSession()
        session.append_text("First.")
        session.append_text("Second.")

        session.begin_next_segment()
        session.mark_current_complete()

        self.assertEqual(
            session.completed_segments,
            ("First.",),
        )
        self.assertEqual(
            session.pending_segments,
            ("Second.",),
        )
        self.assertIsNone(
            session.current_segment
        )

    def test_interruption_preserves_current_segment(
        self,
    ):
        session = StreamedResponseSession()
        session.append_text("Current sentence.")
        session.append_text("Later sentence.")

        session.begin_next_segment()
        session.mark_current_interrupted()

        self.assertTrue(
            session.interrupted
        )
        self.assertEqual(
            session.remaining_text,
            (
                "Current sentence. "
                "Later sentence."
            ),
        )

    def test_interruption_can_store_precise_tts_remainder(
        self,
    ):
        session = StreamedResponseSession()
        session.append_text(
            "The first clause is complete, "
            "but this portion remains."
        )
        session.append_text(
            "This sentence came later."
        )

        session.begin_next_segment()
        session.mark_current_interrupted(
            "but this portion remains."
        )

        self.assertEqual(
            session.pending_segments,
            (
                "but this portion remains.",
                "This sentence came later.",
            ),
        )
        self.assertEqual(
            session.remaining_text,
            (
                "but this portion remains. "
                "This sentence came later."
            ),
        )

    def test_text_can_arrive_after_interruption(
        self,
    ):
        session = StreamedResponseSession()
        session.append_text("Interrupted sentence.")

        session.begin_next_segment()
        session.mark_current_interrupted(
            "Sentence remainder."
        )

        appended = session.append_text(
            "Generated after interruption."
        )

        self.assertTrue(appended)
        self.assertEqual(
            session.remaining_text,
            (
                "Sentence remainder. "
                "Generated after interruption."
            ),
        )

    def test_generated_actions_are_blocked_after_interruption(
        self,
    ):
        session = StreamedResponseSession()
        session.append_text("Some response.")
        session.begin_next_segment()

        self.assertTrue(
            session.can_execute_generated_actions
        )

        session.mark_current_interrupted()

        self.assertFalse(
            session.can_execute_generated_actions
        )

    def test_generation_and_playback_must_both_finish(
        self,
    ):
        session = StreamedResponseSession()
        session.append_text("Only sentence.")
        session.mark_generation_complete()

        self.assertFalse(
            session.is_complete
        )

        session.begin_next_segment()
        session.mark_current_complete()

        self.assertTrue(
            session.is_complete
        )

    def test_append_after_generation_complete_is_rejected(
        self,
    ):
        session = StreamedResponseSession()
        session.mark_generation_complete()

        with self.assertRaises(
            RuntimeError
        ):
            session.append_text(
                "Too late."
            )

    def test_second_segment_cannot_start_while_one_is_active(
        self,
    ):
        session = StreamedResponseSession()
        session.append_text("First.")
        session.append_text("Second.")
        session.begin_next_segment()

        with self.assertRaises(
            RuntimeError
        ):
            session.begin_next_segment()

    def test_segment_cannot_complete_without_being_active(
        self,
    ):
        session = StreamedResponseSession()
        session.append_text("First.")

        with self.assertRaises(
            RuntimeError
        ):
            session.mark_current_complete()

    def test_no_pending_segment_returns_none(
        self,
    ):
        session = StreamedResponseSession()

        self.assertIsNone(
            session.begin_next_segment()
        )

    def test_invalid_completed_count_is_rejected(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            StreamedResponseSession(
                segments=["One."],
                completed_count=2,
            )


if __name__ == "__main__":
    unittest.main()