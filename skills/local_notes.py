from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import LOCAL_DATA_DIR


NOTES_FILE = LOCAL_DATA_DIR / "notes.json"
NOTES_SCHEMA_VERSION = 1
MAX_NOTE_TEXT_LENGTH = 1_000


class LocalNotesError(RuntimeError):
    """Raised when local note storage cannot be read or written safely."""


@dataclass(frozen=True)
class LocalNote:
    """One persistent, offline local note."""

    note_id: int
    text: str
    created_at_utc: str


@dataclass(frozen=True)
class _LocalNoteStore:
    """The internal persisted note collection and next safe identifier."""

    notes: tuple[LocalNote, ...]
    next_id: int


def _utc_now() -> datetime:
    """Return the current UTC time for a new note."""
    return datetime.now(timezone.utc)


def _normalise_note_text(value: str) -> str:
    """Keep note text readable without changing its meaning."""
    if not isinstance(value, str):
        raise LocalNotesError("A note must contain text.")

    text = " ".join(value.split())

    if not text:
        raise LocalNotesError("A note cannot be empty.")

    if len(text) > MAX_NOTE_TEXT_LENGTH:
        raise LocalNotesError(
            f"A note cannot exceed {MAX_NOTE_TEXT_LENGTH} characters."
        )

    return text


def _validate_note_id(value: int) -> int:
    """Accept only a positive integer local-note identifier."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
    ):
        raise LocalNotesError("A local note id must be a positive integer.")

    return value


def _format_utc_timestamp(value: datetime) -> str:
    """Store one timezone-aware datetime in a stable UTC format."""
    if value.tzinfo is None:
        raise LocalNotesError("A note timestamp must include a timezone.")

    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_note(
    raw_note: object,
    *,
    index: int,
) -> LocalNote:
    """Validate one persisted note without silently repairing corruption."""
    if not isinstance(raw_note, dict):
        raise LocalNotesError(
            f"Saved note {index} is not a valid object."
        )

    raw_id = raw_note.get("id")
    raw_text = raw_note.get("text")
    raw_created_at = raw_note.get("created_at_utc")

    try:
        note_id = _validate_note_id(raw_id)
    except LocalNotesError as error:
        raise LocalNotesError(
            f"Saved note {index} has an invalid id."
        ) from error

    text = _normalise_note_text(raw_text)

    if not isinstance(raw_created_at, str):
        raise LocalNotesError(
            f"Saved note {index} has an invalid timestamp."
        )

    try:
        parsed_timestamp = datetime.fromisoformat(
            raw_created_at.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise LocalNotesError(
            f"Saved note {index} has an invalid timestamp."
        ) from error

    if parsed_timestamp.tzinfo is None:
        raise LocalNotesError(
            f"Saved note {index} has an invalid timestamp."
        )

    return LocalNote(
        note_id=note_id,
        text=text,
        created_at_utc=_format_utc_timestamp(parsed_timestamp),
    )


def _parse_next_id(
    raw_next_id: object,
    notes: tuple[LocalNote, ...],
) -> int:
    """Keep note identifiers monotonic, including after deletions."""
    minimum_next_id = max(
        (note.note_id for note in notes),
        default=0,
    ) + 1

    if raw_next_id is None:
        return minimum_next_id

    try:
        next_id = _validate_note_id(raw_next_id)
    except LocalNotesError as error:
        raise LocalNotesError(
            "Local notes have an invalid next_id value."
        ) from error

    if next_id < minimum_next_id:
        raise LocalNotesError(
            "Local notes have an invalid next_id value."
        )

    return next_id


def _load_note_store(
    *,
    note_file: Path,
) -> _LocalNoteStore:
    """Load one validated local-note store without modifying it."""
    path = note_file.expanduser()

    if not path.exists():
        return _LocalNoteStore(
            notes=(),
            next_id=1,
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise LocalNotesError(
            f"Could not read local notes: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise LocalNotesError(
            "Local notes are not valid JSON. They were left unchanged."
        ) from error

    if not isinstance(payload, dict):
        raise LocalNotesError(
            "Local notes have an invalid storage format."
        )

    if payload.get("version") != NOTES_SCHEMA_VERSION:
        raise LocalNotesError(
            "Local notes use an unsupported storage version."
        )

    raw_notes = payload.get("notes")

    if not isinstance(raw_notes, list):
        raise LocalNotesError(
            "Local notes have an invalid notes list."
        )

    notes = tuple(
        _parse_note(raw_note, index=index)
        for index, raw_note in enumerate(raw_notes, start=1)
    )

    note_ids = [note.note_id for note in notes]

    if len(note_ids) != len(set(note_ids)):
        raise LocalNotesError(
            "Local notes contain duplicate ids."
        )

    ordered_notes = tuple(
        sorted(notes, key=lambda note: note.note_id)
    )

    return _LocalNoteStore(
        notes=ordered_notes,
        next_id=_parse_next_id(
            payload.get("next_id"),
            ordered_notes,
        ),
    )


def load_notes(
    *,
    note_file: Path = NOTES_FILE,
) -> tuple[LocalNote, ...]:
    """Load local notes without overwriting missing or damaged data."""
    return _load_note_store(note_file=note_file).notes


def _write_note_store(
    store: _LocalNoteStore,
    *,
    note_file: Path,
) -> None:
    """Atomically replace the notes file only after a full safe write."""
    destination = note_file.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)

    next_id = _parse_next_id(
        store.next_id,
        store.notes,
    )

    payload = {
        "version": NOTES_SCHEMA_VERSION,
        "next_id": next_id,
        "notes": [
            {
                "id": note.note_id,
                "text": note.text,
                "created_at_utc": note.created_at_utc,
            }
            for note in store.notes
        ],
    }

    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=destination.parent,
            suffix=".tmp",
        ) as temporary_file:
            json.dump(payload, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        os.replace(temporary_path, destination)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

        raise LocalNotesError(
            f"Could not save local notes: {error}"
        ) from error


def save_note(
    text: str,
    *,
    note_file: Path = NOTES_FILE,
    now: Callable[[], datetime] = _utc_now,
) -> LocalNote:
    """Create one numbered offline note with an atomic file update."""
    note_text = _normalise_note_text(text)
    store = _load_note_store(note_file=note_file)

    note = LocalNote(
        note_id=store.next_id,
        text=note_text,
        created_at_utc=_format_utc_timestamp(now()),
    )

    _write_note_store(
        _LocalNoteStore(
            notes=(*store.notes, note),
            next_id=note.note_id + 1,
        ),
        note_file=note_file,
    )

    return note


def delete_note(
    note_id: int,
    *,
    expected_note: LocalNote | None = None,
    note_file: Path = NOTES_FILE,
) -> LocalNote:
    """Delete one exact note id while preserving all other notes."""
    requested_id = _validate_note_id(note_id)
    store = _load_note_store(note_file=note_file)

    target = next(
        (
            note
            for note in store.notes
            if note.note_id == requested_id
        ),
        None,
    )

    if target is None:
        raise LocalNotesError(
            f"Local note {requested_id} does not exist."
        )

    if expected_note is not None:
        if not isinstance(expected_note, LocalNote):
            raise LocalNotesError(
                "Expected local note data is invalid."
            )

        if target != expected_note:
            raise LocalNotesError(
                "Local note changed since the delete request."
            )

    remaining_notes = tuple(
        note
        for note in store.notes
        if note.note_id != requested_id
    )

    _write_note_store(
        _LocalNoteStore(
            notes=remaining_notes,
            next_id=store.next_id,
        ),
        note_file=note_file,
    )

    return target


def search_notes(
    query: str,
    *,
    note_file: Path = NOTES_FILE,
) -> tuple[LocalNote, ...]:
    """Find case-insensitive literal text matches in local notes."""
    normalized_query = _normalise_note_text(query).casefold()

    return tuple(
        note
        for note in load_notes(note_file=note_file)
        if normalized_query in note.text.casefold()
    )


def format_notes(
    notes: Iterable[LocalNote],
) -> str:
    """Format a readable numbered local-note list for console output."""
    note_list = tuple(sorted(notes, key=lambda note: note.note_id))

    lines = [
        "Avens Local Notes",
        f"Notes: {len(note_list)}",
        "",
    ]

    if not note_list:
        lines.append("- No local notes saved.")
    else:
        for note in note_list:
            lines.append(
                f"{note.note_id}. "
                f"[{note.created_at_utc}] "
                f"{note.text}"
            )

    return "\n".join(lines)


def format_note_search(
    query: str,
    notes: Iterable[LocalNote],
) -> str:
    """Format one deterministic local-note search result."""
    normalized_query = _normalise_note_text(query)
    note_list = tuple(sorted(notes, key=lambda note: note.note_id))

    lines = [
        f'Local note search: "{normalized_query}"',
        f"Matches: {len(note_list)}",
    ]

    if not note_list:
        lines.append("- None")
    else:
        for note in note_list:
            lines.append(
                f"{note.note_id}. "
                f"[{note.created_at_utc}] "
                f"{note.text}"
            )

    return "\n".join(lines)