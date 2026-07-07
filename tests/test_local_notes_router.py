from __future__ import annotations

import unittest

from skills.local_notes import (
    LocalNote,
    LocalNotesError,
)

from skills.note_delete_confirmation import (
    NoteDeleteConfirmationStore,
)

from skills.router import route_local_skill


def make_note(
    note_id: int,
    text: str,
) -> LocalNote:
    """Build one stable test note."""
    return LocalNote(
        note_id=note_id,
        text=text,
        created_at_utc="2026-07-07T08:30:00Z",
    )


class LocalNotesRouterTests(unittest.TestCase):

    def test_delete_note_requires_confirmation_before_deletion(self):
        output = []
        delete_calls = []
        note = make_note(2, "Finish Avens tests")
        store = NoteDeleteConfirmationStore(
            clock=lambda: 100.0,
            timeout_seconds=15.0,
        )

        result = route_local_skill(
            "Delete note 2",
            load_local_notes=lambda: (note,),
            delete_local_note=lambda *args, **kwargs: (
                delete_calls.append((args, kwargs))
            ),
            note_delete_confirmations=store,
            console_output=output.append,
        )

        self.assertEqual(delete_calls, [])
        self.assertEqual(result.skill_name, "delete_local_note")
        self.assertTrue(result.requires_confirmation)
        self.assertIn(
            'Confirm delete note 2',
            result.message,
        )

    def test_confirm_delete_note_uses_exact_pending_snapshot(self):
        note = make_note(2, "Finish Avens tests")
        store = NoteDeleteConfirmationStore(
            clock=lambda: 100.0,
            timeout_seconds=15.0,
        )
        store.begin(note)
        deleted = []

        def delete_local_note(
            note_id: int,
            *,
            expected_note: LocalNote,
        ) -> LocalNote:
            deleted.append((note_id, expected_note))
            return expected_note

        result = route_local_skill(
            "Confirm delete note 2",
            delete_local_note=delete_local_note,
            note_delete_confirmations=store,
        )

        self.assertEqual(deleted, [(2, note)])
        self.assertEqual(
            result.message,
            "Deleted local note 2, sir.",
        )

    def test_mismatched_note_delete_confirmation_cancels_request(self):
        note = make_note(2, "Finish Avens tests")
        store = NoteDeleteConfirmationStore(
            clock=lambda: 100.0,
            timeout_seconds=15.0,
        )
        store.begin(note)
        delete_calls = []

        result = route_local_skill(
            "Confirm delete note 1",
            delete_local_note=lambda *args, **kwargs: (
                delete_calls.append((args, kwargs))
            ),
            note_delete_confirmations=store,
        )

        self.assertEqual(delete_calls, [])
        self.assertIn("did not match", result.message)
        self.assertEqual(store.confirm(2).status, "none")

    def test_cancel_delete_note_clears_the_pending_request(self):
        note = make_note(2, "Finish Avens tests")
        store = NoteDeleteConfirmationStore(
            clock=lambda: 100.0,
            timeout_seconds=15.0,
        )
        store.begin(note)

        result = route_local_skill(
            "Cancel delete note",
            note_delete_confirmations=store,
        )

        self.assertEqual(
            result.message,
            "Pending deletion of local note 2 cancelled, sir.",
        )
        self.assertEqual(store.confirm(2).status, "none")

    def test_delete_unknown_note_is_refused_without_confirmation(self):
        result = route_local_skill(
            "Delete note 99",
            load_local_notes=lambda: (),
        )

        self.assertEqual(result.skill_name, "delete_local_note")
        self.assertEqual(
            result.message,
            "I could not find local note 99, sir.",
        )

    def test_take_a_note_saves_exact_text_without_ai_rewriting(self):
        output = []
        saved_text = []

        def save_local_note(text: str) -> LocalNote:
            saved_text.append(text)
            return make_note(1, text)

        result = route_local_skill(
            "Take a note buy chicken tomorrow",
            save_local_note=save_local_note,
            console_output=output.append,
        )

        self.assertEqual(
            saved_text,
            ["buy chicken tomorrow"],
        )
        self.assertEqual(
            result.skill_name,
            "create_local_note",
        )
        self.assertEqual(
            result.message,
            "Saved local note 1, sir.",
        )
        self.assertIn(
            "Saved local note 1: buy chicken tomorrow",
            "\n".join(output),
        )

    def test_add_note_uses_the_same_safe_create_skill(self):
        result = route_local_skill(
            "Add note finish Avens tests",
            save_local_note=lambda text: make_note(2, text),
        )

        self.assertEqual(
            result.skill_name,
            "create_local_note",
        )
        self.assertEqual(
            result.message,
            "Saved local note 2, sir.",
        )

    def test_show_my_notes_prints_a_numbered_list(self):
        output = []

        result = route_local_skill(
            "Show my notes",
            load_local_notes=lambda: (
                make_note(1, "Buy chicken tomorrow"),
                make_note(2, "Finish Avens tests"),
            ),
            console_output=output.append,
        )

        self.assertEqual(
            result.skill_name,
            "list_local_notes",
        )
        self.assertIn(
            "1. [2026-07-07T08:30:00Z] Buy chicken tomorrow",
            "\n".join(output),
        )
        self.assertEqual(
            result.message,
            "I printed 2 local notes, sir.",
        )

    def test_list_notes_handles_an_empty_note_store(self):
        output = []

        result = route_local_skill(
            "List notes",
            load_local_notes=lambda: (),
            console_output=output.append,
        )

        self.assertEqual(
            result.skill_name,
            "list_local_notes",
        )
        self.assertIn(
            "- No local notes saved.",
            "\n".join(output),
        )
        self.assertEqual(
            result.message,
            "You have no saved local notes, sir.",
        )

    def test_search_notes_prints_deterministic_matches(self):
        output = []
        searched_queries = []

        def find_local_notes(query: str) -> tuple[LocalNote, ...]:
            searched_queries.append(query)
            return (make_note(1, "Buy chicken tomorrow"),)

        result = route_local_skill(
            "Search notes chicken",
            find_local_notes=find_local_notes,
            console_output=output.append,
        )

        self.assertEqual(searched_queries, ["chicken"])
        self.assertEqual(
            result.skill_name,
            "search_local_notes",
        )
        self.assertIn(
            'Local note search: "chicken"',
            "\n".join(output),
        )
        self.assertEqual(
            result.message,
            (
                "I found 1 local notes matching chicken. "
                "I printed the details, sir."
            ),
        )

    def test_note_storage_errors_are_handled_without_falling_back(self):
        output = []

        def fail_to_save(_: str) -> LocalNote:
            raise LocalNotesError("test storage error")

        result = route_local_skill(
            "Take a note do not lose this",
            save_local_note=fail_to_save,
            console_output=output.append,
        )

        self.assertEqual(
            result.skill_name,
            "create_local_note",
        )
        self.assertEqual(
            result.message,
            "I could not save that local note safely, sir.",
        )
        self.assertIn(
            "Local notes error: test storage error",
            "\n".join(output),
        )