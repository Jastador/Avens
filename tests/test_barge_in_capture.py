from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from core.barge_in import (
    CapturedBargeIn,
    SpeechCandidateRecorder,
    _store_barge_result,
    analyse_recorded_barge_in,
    _clear_barge_result
)
from core.barge_intent import (
    BargeInIntent,
)


def audio_block(
    value: float,
    size: int = 4,
) -> np.ndarray:
    return np.full(
        size,
        value,
        dtype=np.float32,
    )


class SpeechCandidateRecorderTests(
    unittest.TestCase
):
    def create_recorder(
        self,
        **overrides,
    ) -> SpeechCandidateRecorder:
        options = {
            "start_threshold": 0.5,
            "end_threshold": 0.2,
            "required_start_hits": 3,
            "required_silence_blocks": 2,
            "maximum_capture_blocks": 10,
            "pre_roll_blocks": 4,
        }
        options.update(overrides)

        return SpeechCandidateRecorder(
            **options
        )

    def test_loud_blocks_must_be_consecutive(
        self,
    ):
        recorder = self.create_recorder()

        energies = [
            0.7,
            0.8,
            0.1,
            0.7,
            0.8,
        ]

        for energy in energies:
            recorder.add_block(
                audio_block(energy),
                energy,
            )

        self.assertFalse(
            recorder.triggered
        )

    def test_required_hits_trigger_capture(
        self,
    ):
        recorder = self.create_recorder()

        events = [
            recorder.add_block(
                audio_block(0.7),
                0.7,
            )
            for _ in range(3)
        ]

        self.assertEqual(
            events[-1],
            "triggered",
        )
        self.assertTrue(
            recorder.triggered
        )

    def test_trigger_includes_pre_roll(
        self,
    ):
        recorder = self.create_recorder()

        recorder.add_block(
            audio_block(0.1),
            0.1,
        )

        for _ in range(3):
            recorder.add_block(
                audio_block(0.7),
                0.7,
            )

        self.assertEqual(
            len(recorder.recorded_blocks),
            4,
        )

    def test_trailing_silence_finishes_capture(
        self,
    ):
        recorder = self.create_recorder()

        for _ in range(3):
            recorder.add_block(
                audio_block(0.7),
                0.7,
            )

        first_silence = recorder.add_block(
            audio_block(0.0),
            0.0,
        )
        second_silence = recorder.add_block(
            audio_block(0.0),
            0.0,
        )

        self.assertEqual(
            first_silence,
            "capturing",
        )
        self.assertEqual(
            second_silence,
            "finished",
        )
        self.assertTrue(
            recorder.finished
        )

    def test_voice_resets_trailing_silence(
        self,
    ):
        recorder = self.create_recorder()

        for _ in range(3):
            recorder.add_block(
                audio_block(0.7),
                0.7,
            )

        recorder.add_block(
            audio_block(0.0),
            0.0,
        )
        recorder.add_block(
            audio_block(0.7),
            0.7,
        )
        event = recorder.add_block(
            audio_block(0.0),
            0.0,
        )

        self.assertEqual(
            event,
            "capturing",
        )
        self.assertFalse(
            recorder.finished
        )

    def test_maximum_capture_length_finishes(
        self,
    ):
        recorder = self.create_recorder(
            required_start_hits=2,
            maximum_capture_blocks=5,
        )

        recorder.add_block(
            audio_block(0.1),
            0.1,
        )
        recorder.add_block(
            audio_block(0.7),
            0.7,
        )
        recorder.add_block(
            audio_block(0.7),
            0.7,
        )
        recorder.add_block(
            audio_block(0.7),
            0.7,
        )

        event = recorder.add_block(
            audio_block(0.7),
            0.7,
        )

        self.assertEqual(
            event,
            "finished",
        )
        self.assertTrue(
            recorder.finished
        )

    def test_audio_returns_flat_float_array(
        self,
    ):
        recorder = self.create_recorder()

        for _ in range(3):
            recorder.add_block(
                audio_block(0.7),
                0.7,
            )

        captured = recorder.audio()

        self.assertEqual(
            captured.dtype,
            np.float32,
        )
        self.assertEqual(
            captured.ndim,
            1,
        )
        self.assertEqual(
            captured.size,
            12,
        )

    def test_recorded_audio_is_transcribed_and_classified(
        self,
    ):
        with patch(
            "core.barge_in.transcribe_recorded_audio",
            return_value=(
                "Wait, what do you mean by local data?"
            ),
        ):
            result = analyse_recorded_barge_in(
                audio_block(0.5),
                spoken_text=(
                    "Offline models store data locally."
                ),
            )

        self.assertEqual(
            result.transcript,
            "Wait, what do you mean by local data?",
        )
        self.assertEqual(
            result.decision.intent,
            BargeInIntent.DIRECTED,
        )

    def test_result_is_stored_in_shared_state(
        self,
    ):
        with patch(
            "core.barge_in.transcribe_recorded_audio",
            return_value="Hmm.",
        ):
            result = analyse_recorded_barge_in(
                audio_block(0.5),
            )

        shared_state = {}

        _store_barge_result(
            shared_state,
            result,
        )

        self.assertTrue(
            shared_state["barge_in_ready"]
        )
        self.assertEqual(
            shared_state["barge_in_transcript"],
            "Hmm.",
        )
        self.assertEqual(
            shared_state["barge_in_intent"],
            "acknowledgement",
        )
        self.assertEqual(
            shared_state["barge_in_status"],
            "ready",
        )

    def test_empty_transcript_becomes_unclear(
        self,
    ):
        with patch(
            "core.barge_in.transcribe_recorded_audio",
            return_value="",
        ):
            result = analyse_recorded_barge_in(
                audio_block(0.5),
            )

        self.assertIsInstance(
            result,
            CapturedBargeIn,
        )
        self.assertEqual(
            result.decision.intent,
            BargeInIntent.UNCLEAR,
        )

    def test_clear_result_blocks_transcription(
        self,
    ):
        shared_state = {
            "barge_in_allow_transcription": True,
        }

        _clear_barge_result(
            shared_state
        )

        self.assertFalse(
            shared_state[
                "barge_in_allow_transcription"
            ]
        )
        self.assertFalse(
            shared_state["barge_in_ready"]
        )
        self.assertEqual(
            shared_state["barge_in_status"],
            "listening",
        )


if __name__ == "__main__":
    unittest.main()