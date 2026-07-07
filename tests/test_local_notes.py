from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skills.local_notes import (
    LocalNotesError,
    format_note_search,
    format_notes,
    load_notes,
    save_note,
    search_notes,
    delete_note,
)


class LocalNotesTests(unittest.TestCase):

    def test_delete_note_preserves_other_notes_and_future_ids(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"

            first = save_note(
                "First note",
                note_file=note_file,
                now=lambda: self.created_at,
            )
            second = save_note(
                "Second note",
                note_file=note_file,
                now=lambda: self.created_at,
            )

            deleted = delete_note(
                first.note_id,
                note_file=note_file,
            )

            third = save_note(
                "Third note",
                note_file=note_file,
                now=lambda: self.created_at,
            )

            remaining_notes = load_notes(note_file=note_file)

        self.assertEqual(deleted.note_id, 1)
        self.assertEqual(second.note_id, 2)
        self.assertEqual(third.note_id, 3)
        self.assertEqual(
            [note.note_id for note in remaining_notes],
            [2, 3],
        )

    def test_delete_unknown_note_is_rejected_without_changing_storage(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"

            save_note(
                "Keep this note",
                note_file=note_file,
                now=lambda: self.created_at,
            )
            original_text = note_file.read_text(encoding="utf-8")

            with self.assertRaisesRegex(
                LocalNotesError,
                "does not exist",
            ):
                delete_note(
                    99,
                    note_file=note_file,
                )

            self.assertEqual(
                note_file.read_text(encoding="utf-8"),
                original_text,
            )

    def setUp(self):
        self.created_at = datetime(
            2026,
            7,
            7,
            8,
            30,
            tzinfo=timezone.utc,
        )

    def test_save_note_creates_a_numbered_json_note(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"

            note = save_note(
                "  Buy   chicken tomorrow.  ",
                note_file=note_file,
                now=lambda: self.created_at,
            )

            payload = json.loads(
                note_file.read_text(encoding="utf-8")
            )

        self.assertEqual(note.note_id, 1)
        self.assertEqual(note.text, "Buy chicken tomorrow.")
        self.assertEqual(
            note.created_at_utc,
            "2026-07-07T08:30:00Z",
        )
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["next_id"], 2)
        self.assertEqual(payload["notes"][0]["id"], 1)

    def test_save_note_keeps_incrementing_ids(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"

            first = save_note(
                "First note",
                note_file=note_file,
                now=lambda: self.created_at,
            )
            second = save_note(
                "Second note",
                note_file=note_file,
                now=lambda: self.created_at,
            )

        self.assertEqual(first.note_id, 1)
        self.assertEqual(second.note_id, 2)

    def test_load_notes_returns_notes_in_id_order(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"

            note_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "notes": [
                            {
                                "id": 2,
                                "text": "Second",
                                "created_at_utc": (
                                    "2026-07-07T08:30:00Z"
                                ),
                            },
                            {
                                "id": 1,
                                "text": "First",
                                "created_at_utc": (
                                    "2026-07-07T08:29:00Z"
                                ),
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            notes = load_notes(note_file=note_file)

        self.assertEqual(
            [note.note_id for note in notes],
            [1, 2],
        )

    def test_search_notes_uses_literal_case_insensitive_matching(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"

            save_note(
                "Buy chicken tomorrow",
                note_file=note_file,
                now=lambda: self.created_at,
            )
            save_note(
                "Finish Avens tests",
                note_file=note_file,
                now=lambda: self.created_at,
            )

            matches = search_notes(
                "CHICKEN",
                note_file=note_file,
            )

        self.assertEqual(
            [note.text for note in matches],
            ["Buy chicken tomorrow"],
        )

    def test_empty_note_is_rejected(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"

            with self.assertRaisesRegex(
                LocalNotesError,
                "cannot be empty",
            ):
                save_note(
                    "   ",
                    note_file=note_file,
                    now=lambda: self.created_at,
                )

    def test_corrupt_notes_are_not_overwritten(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"
            original_text = "{not valid json"

            note_file.write_text(
                original_text,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                LocalNotesError,
                "not valid JSON",
            ):
                save_note(
                    "Do not overwrite this",
                    note_file=note_file,
                    now=lambda: self.created_at,
                )

            self.assertEqual(
                note_file.read_text(encoding="utf-8"),
                original_text,
            )

    def test_formatters_show_note_ids_and_empty_results(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"

            note = save_note(
                "Finish Avens tests",
                note_file=note_file,
                now=lambda: self.created_at,
            )

        self.assertIn(
            "1. [2026-07-07T08:30:00Z] Finish Avens tests",
            format_notes((note,)),
        )
        self.assertIn(
            'Local note search: "chicken"',
            format_note_search("chicken", ()),
        )
        self.assertIn(
            "- None",
            format_note_search("chicken", ()),
        )

    def test_delete_note_refuses_a_changed_pending_note(self):
        with TemporaryDirectory() as temporary_directory:
            note_file = Path(temporary_directory) / "notes.json"

            saved_note = save_note(
                "Original note",
                note_file=note_file,
                now=lambda: self.created_at,
            )

            payload = json.loads(
                note_file.read_text(encoding="utf-8")
            )
            payload["notes"][0]["text"] = "Changed note"

            note_file.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                LocalNotesError,
                "changed since",
            ):
                delete_note(
                    saved_note.note_id,
                    expected_note=saved_note,
                    note_file=note_file,
                )

            notes = load_notes(note_file=note_file)

        self.assertEqual(notes[0].text, "Changed note")