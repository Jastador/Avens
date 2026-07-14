from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

import core.stt as stt


class RecordedAudioTranscriptionTests(
    unittest.TestCase
):
    def test_empty_audio_returns_empty_text(
        self,
    ):
        with patch.object(
            stt,
            "init_model",
        ) as init_model:
            result = stt.transcribe_recorded_audio(
                [],
            )

        self.assertEqual(result, "")
        init_model.assert_not_called()

    def test_invalid_audio_returns_empty_text(
        self,
    ):
        with patch.object(
            stt,
            "init_model",
        ) as init_model:
            result = stt.transcribe_recorded_audio(
                ["not audio"],
            )

        self.assertEqual(result, "")
        init_model.assert_not_called()

    def test_non_finite_audio_returns_empty_text(
        self,
    ):
        audio = np.array(
            [0.1, np.nan, 0.2],
            dtype=np.float32,
        )

        with patch.object(
            stt,
            "init_model",
        ) as init_model:
            result = stt.transcribe_recorded_audio(
                audio,
            )

        self.assertEqual(result, "")
        init_model.assert_not_called()

    def test_existing_model_transcribes_audio(
        self,
    ):
        fake_model = object()

        with (
            patch.object(
                stt,
                "model",
                fake_model,
            ),
            patch.object(
                stt,
                "_transcribe_audio",
                return_value="Wait, what do you mean?",
            ) as transcribe,
        ):
            result = stt.transcribe_recorded_audio(
                np.array(
                    [0.1, 0.2, 0.3],
                    dtype=np.float64,
                ),
            )

        self.assertEqual(
            result,
            "Wait, what do you mean?",
        )

        audio_argument = transcribe.call_args.args[0]

        self.assertEqual(
            audio_argument.dtype,
            np.float32,
        )
        self.assertEqual(
            audio_argument.ndim,
            1,
        )
        self.assertFalse(
            transcribe.call_args.kwargs[
                "command_aware"
            ]
        )

    def test_nested_audio_is_flattened(
        self,
    ):
        fake_model = object()

        with (
            patch.object(
                stt,
                "model",
                fake_model,
            ),
            patch.object(
                stt,
                "_transcribe_audio",
                return_value="Hello.",
            ) as transcribe,
        ):
            result = stt.transcribe_recorded_audio(
                [
                    [0.1],
                    [0.2],
                    [0.3],
                ],
            )

        self.assertEqual(result, "Hello.")

        audio_argument = transcribe.call_args.args[0]

        self.assertEqual(
            audio_argument.shape,
            (3,),
        )

    def test_missing_model_is_initialized(
        self,
    ):
        fake_model = object()

        def initialize_fake_model():
            stt.model = fake_model

        with (
            patch.object(
                stt,
                "model",
                None,
            ),
            patch.object(
                stt,
                "init_model",
                side_effect=initialize_fake_model,
            ) as init_model,
            patch.object(
                stt,
                "_transcribe_audio",
                return_value="Avens, stop.",
            ) as transcribe,
        ):
            result = stt.transcribe_recorded_audio(
                [0.1, 0.2],
            )

        self.assertEqual(
            result,
            "Avens, stop.",
        )
        init_model.assert_called_once_with()
        transcribe.assert_called_once()

    def test_unavailable_model_returns_empty_text(
        self,
    ):
        with (
            patch.object(
                stt,
                "model",
                None,
            ),
            patch.object(
                stt,
                "init_model",
            ) as init_model,
            patch.object(
                stt,
                "_transcribe_audio",
            ) as transcribe,
        ):
            result = stt.transcribe_recorded_audio(
                [0.1, 0.2],
            )

        self.assertEqual(result, "")
        init_model.assert_called_once_with()
        transcribe.assert_not_called()

    def test_command_aware_option_is_forwarded(
        self,
    ):
        fake_model = object()

        with (
            patch.object(
                stt,
                "model",
                fake_model,
            ),
            patch.object(
                stt,
                "_transcribe_audio",
                return_value="Open Discord.",
            ) as transcribe,
        ):
            result = stt.transcribe_recorded_audio(
                [0.1, 0.2],
                command_aware=True,
            )

        self.assertEqual(
            result,
            "Open Discord.",
        )
        self.assertTrue(
            transcribe.call_args.kwargs[
                "command_aware"
            ]
        )

    def test_decode_failure_returns_empty_text(
        self,
    ):
        fake_model = object()

        with (
            patch.object(
                stt,
                "model",
                fake_model,
            ),
            patch.object(
                stt,
                "_transcribe_audio",
                side_effect=RuntimeError(
                    "decode failed"
                ),
            ),
        ):
            result = stt.transcribe_recorded_audio(
                [0.1, 0.2],
            )

        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()