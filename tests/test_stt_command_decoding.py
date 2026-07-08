from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from core import stt


class FakeWhisperModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def transcribe(self, audio_data, **options):
        self.calls.append((audio_data, options))
        response = next(self.responses)

        if isinstance(response, Exception):
            raise response

        return [SimpleNamespace(text=response)], {}


class SttCommandDecodingTests(unittest.TestCase):
    def setUp(self):
        self.previous_model = stt.model
        self.audio_data = object()

    def tearDown(self):
        stt.model = self.previous_model

    def test_command_decode_uses_command_hints(self):
        fake_model = FakeWhisperModel(["Open Notepad."])
        stt.model = fake_model

        text = stt._transcribe_audio(
            self.audio_data,
            command_aware=True,
        )

        self.assertEqual(text, "Open Notepad.")
        self.assertEqual(
            fake_model.calls,
            [
                (
                    self.audio_data,
                    {
                        "language": "en",
                        "beam_size": 5,
                        "vad_filter": True,
                        "condition_on_previous_text": False,
                        "hotwords": stt.STT_COMMAND_HOTWORDS,
                        "initial_prompt": (
                            stt.STT_COMMAND_INITIAL_PROMPT
                        ),
                    },
                ),
            ],
        )

    def test_runtime_command_hints_include_local_file_discovery_once(self):
        self.assertIn(
            "set volume",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "night light settings",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "Set volume to 70.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "Start reading setup.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "set a timer",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "start a timer",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "Start a timer for 45 seconds.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "cancel reminder",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "Set a timer for 5 minutes.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "Remind me tomorrow at 8 PM to call Dad.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "Confirm cancel reminder 2.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "find file",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "search files",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "what files can you search",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "Find file Avens roadmap.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "What files can you search?",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "Ollama",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "Search files portable Ollama.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertNotIn(
            "Go to sleep.Delete note",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertEqual(
            stt.STT_COMMAND_HOTWORDS.count(
                "Notepad, Calculator"
            ),
            1,
        )
        self.assertEqual(
            stt.STT_COMMAND_INITIAL_PROMPT.count(
                "Voice commands include:"
            ),
            1,
        )
        self.assertIn(
            "NitroSense",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "max out NitroSense fans",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "confirm NitroSense gaming profile",
            stt.STT_COMMAND_HOTWORDS,
        )
        self.assertIn(
            "Set NitroSense gaming profile.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "Confirm NitroSense gaming profile.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "Cancel NitroSense gaming profile.",
            stt.STT_COMMAND_INITIAL_PROMPT,
        )

    def test_generic_decode_uses_no_command_hints(self):
        fake_model = FakeWhisperModel(["What time is it?"])
        stt.model = fake_model

        text = stt._transcribe_audio(
            self.audio_data,
            command_aware=False,
        )

        self.assertEqual(text, "What time is it?")
        self.assertEqual(
            fake_model.calls,
            [
                (
                    self.audio_data,
                    {
                        "language": "en",
                        "beam_size": 5,
                        "vad_filter": True,
                    },
                ),
            ],
        )

    def test_collapses_only_identical_repeated_sentences(self):
        self.assertEqual(
            stt._collapse_exact_repeated_sentences(
                "Open Notepad. Open Notepad."
            ),
            "Open Notepad",
        )

    def test_keeps_non_identical_sentences_unchanged(self):
        self.assertEqual(
            stt._collapse_exact_repeated_sentences(
                "Open Notepad. Open Calculator."
            ),
            "Open Notepad. Open Calculator.",
        )

    def test_command_path_uses_only_one_decode(self):
        with patch.object(
            stt,
            "_transcribe_audio",
            return_value="Open Notepad. Open Notepad.",
        ) as transcribe_audio, patch.object(
            stt,
            "_is_explicit_local_skill_request",
            return_value=True,
        ):
            decision = stt._decode_audio_for_turn(self.audio_data)

        self.assertEqual(decision.text, "Open Notepad")
        self.assertEqual(decision.decode_path, "command")
        self.assertIsNone(decision.generic_decode_seconds)
        self.assertEqual(
            transcribe_audio.call_args_list,
            [
                call(
                    self.audio_data,
                    command_aware=True,
                ),
            ],
        )

    def test_partial_command_candidate_falls_back_to_generic_decode(self):
        with patch.object(
            stt,
            "_transcribe_audio",
            side_effect=[
                "Notepad.",
                "What does Notepad do?",
            ],
        ) as transcribe_audio, patch.object(
            stt,
            "_is_explicit_local_skill_request",
            return_value=False,
        ):
            decision = stt._decode_audio_for_turn(self.audio_data)

        self.assertEqual(
            decision.text,
            "What does Notepad do?",
        )
        self.assertEqual(decision.decode_path, "generic")
        self.assertIsNotNone(decision.generic_decode_seconds)
        self.assertEqual(
            transcribe_audio.call_args_list,
            [
                call(
                    self.audio_data,
                    command_aware=True,
                ),
                call(
                    self.audio_data,
                    command_aware=False,
                ),
            ],
        )

    def test_command_decode_error_falls_back_to_generic_decode(self):
        with patch.object(
            stt,
            "_transcribe_audio",
            side_effect=[
                RuntimeError("command decode failed"),
                "What time is it?",
            ],
        ) as transcribe_audio, patch.object(
            stt,
            "_is_explicit_local_skill_request",
        ) as is_explicit_request:
            decision = stt._decode_audio_for_turn(self.audio_data)

        self.assertEqual(decision.text, "What time is it?")
        self.assertEqual(decision.decode_path, "generic")
        is_explicit_request.assert_not_called()
        self.assertEqual(
            transcribe_audio.call_args_list,
            [
                call(
                    self.audio_data,
                    command_aware=True,
                ),
                call(
                    self.audio_data,
                    command_aware=False,
                ),
            ],
        )