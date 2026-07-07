from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.benchmark_stt_commands import (
    CommandSample,
    SampleResult,
    build_summary,
    is_exact_command_match,
    load_samples,
    normalize_command_text,
    COMMAND_HOTWORDS,
    COMMAND_INITIAL_PROMPT,
    PHRASE_SETS,
)

class CommandBenchmarkTests(unittest.TestCase):

    def test_command_hints_include_system_controls_and_reminders_once(self):
        self.assertIn(
            "set volume to 70",
            PHRASE_SETS["commands"],
        )
        self.assertIn(
            "open night light settings",
            PHRASE_SETS["commands"],
        )
        self.assertIn(
            "set a timer for 5 minutes",
            PHRASE_SETS["commands"],
        )
        self.assertIn(
            "remind me tomorrow at 8 pm to call dad",
            PHRASE_SETS["commands"],
        )
        self.assertIn(
            "cancel reminder 2",
            PHRASE_SETS["commands"],
        )
        self.assertIn(
            "set a timer",
            COMMAND_HOTWORDS,
        )
        self.assertIn(
            "Set a timer for 5 minutes.",
            COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "start a timer for 45 seconds",
            PHRASE_SETS["commands"],
        )
        self.assertIn(
            "start a timer",
            COMMAND_HOTWORDS,
        )
        self.assertIn(
            "Start a timer for 45 seconds.",
            COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "Confirm cancel reminder 2.",
            COMMAND_INITIAL_PROMPT,
        )
        self.assertIn(
            "Set volume to 70.",
            COMMAND_INITIAL_PROMPT,
        )
        self.assertNotIn(
            "Go to sleep.Delete note 2.",
            COMMAND_INITIAL_PROMPT,
        )
        self.assertEqual(
            COMMAND_INITIAL_PROMPT.count("Voice commands include:"),
            1,
        )
        self.assertEqual(
            COMMAND_HOTWORDS.count("Notepad, Calculator"),
            1,
        )

    def test_command_benchmark_includes_note_deletion_terms(self):
        self.assertIn(
            "delete note 2",
            PHRASE_SETS["commands"],
        )
        self.assertIn(
            "confirm delete note",
            COMMAND_HOTWORDS,
        )
        self.assertIn(
            "Confirm delete note 2.",
            COMMAND_INITIAL_PROMPT,
        )

    def test_command_benchmark_includes_local_note_terms(self):
        self.assertIn(
            "take a note buy chicken tomorrow",
            PHRASE_SETS["commands"],
        )
        self.assertIn("search notes", COMMAND_HOTWORDS)
        self.assertIn(
            "Take a note buy chicken tomorrow.",
            COMMAND_INITIAL_PROMPT,
        )

    def test_command_benchmark_includes_catalog_inspection_terms(self):
        self.assertIn("list apps", PHRASE_SETS["commands"])
        self.assertIn("search apps", COMMAND_HOTWORDS)
        self.assertIn(
            "What can I control?",
            COMMAND_INITIAL_PROMPT,
        )

    def test_normalize_command_text_ignores_case_and_punctuation(self):
        self.assertEqual(
            normalize_command_text("  Open, Notepad!  "),
            "open notepad",
        )

    def test_exact_command_match_requires_all_words(self):
        self.assertTrue(
            is_exact_command_match(
                "open notepad",
                "Open Notepad.",
            )
        )
        self.assertFalse(
            is_exact_command_match(
                "open notepad",
                "open node pad",
            )
        )

    def test_load_samples_reads_a_valid_manifest(self):
        with TemporaryDirectory() as temporary_directory:
            sample_directory = Path(temporary_directory)
            audio_file = sample_directory / "command_01_take_01.wav"
            audio_file.write_bytes(b"test audio")

            manifest_path = sample_directory / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "samples": [
                            {
                                "expected_text": "open notepad",
                                "audio_file": audio_file.name,
                                "take": 1,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            samples = load_samples(sample_directory)

        self.assertEqual(
            samples,
            [
                CommandSample(
                    expected_text="open notepad",
                    audio_file="command_01_take_01.wav",
                    take=1,
                ),
            ],
        )

    def test_load_samples_rejects_missing_audio_file(self):
        with TemporaryDirectory() as temporary_directory:
            sample_directory = Path(temporary_directory)
            manifest_path = sample_directory / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "samples": [
                            {
                                "expected_text": "open notepad",
                                "audio_file": "missing.wav",
                                "take": 1,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                FileNotFoundError,
                "missing.wav",
            ):
                load_samples(sample_directory)

    def test_load_samples_rejects_an_empty_manifest(self):
        with TemporaryDirectory() as temporary_directory:
            sample_directory = Path(temporary_directory)
            manifest_path = sample_directory / "manifest.json"
            manifest_path.write_text(
                json.dumps({"samples": []}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "non-empty",
            ):
                load_samples(sample_directory)

    def test_build_summary_calculates_exact_rate_and_decode_average(self):
        results = [
            SampleResult(
                model_name="distil-small.en",
                expected_text="open notepad",
                audio_file="one.wav",
                take=1,
                transcription="open notepad",
                normalized_transcription="open notepad",
                exact_match=True,
                decode_seconds=0.2,
            ),
            SampleResult(
                model_name="distil-small.en",
                expected_text="open notepad",
                audio_file="two.wav",
                take=2,
                transcription="open node pad",
                normalized_transcription="open node pad",
                exact_match=False,
                decode_seconds=0.4,
            ),
        ]

        self.assertEqual(
            build_summary(results),
            {
                "total_samples": 2,
                "exact_matches": 1,
                "exact_match_rate": 0.5,
                "average_decode_seconds": 0.3,
            },
        )