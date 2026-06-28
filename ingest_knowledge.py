from __future__ import annotations

import os
from pathlib import Path

from config import LOCAL_DATA_DIR
from core.memory import save_memory


DEFAULT_KNOWLEDGE_DIR = LOCAL_DATA_DIR / "knowledge_base"

KNOWLEDGE_DIR = Path(
    os.getenv("AVENS_KNOWLEDGE_DIR", str(DEFAULT_KNOWLEDGE_DIR))
).expanduser()

SUPPORTED_SUFFIXES = {".md", ".txt"}


def chunk_text(text: str, max_words: int = 100, overlap: int = 20) -> list[str]:
    """Split documents into overlapping chunks for vector-memory ingestion."""
    if max_words <= overlap:
        raise ValueError("max_words must be greater than overlap.")

    words = text.split()
    step = max_words - overlap

    return [
        " ".join(words[index:index + max_words])
        for index in range(0, len(words), step)
        if words[index:index + max_words]
    ]


def iter_knowledge_files() -> list[Path]:
    if not KNOWLEDGE_DIR.exists():
        return []

    return sorted(
        path
        for path in KNOWLEDGE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def ingest_documents() -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    files = iter_knowledge_files()

    if not files:
        print(
            f"No documents found in '{KNOWLEDGE_DIR}'. "
            "Add .md or .txt files there and run this script again."
        )
        return

    print(f"Found {len(files)} documents. Beginning ingestion...")
    total_chunks = 0

    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as error:
            print(f"Skipping '{file_path.name}': {error}")
            continue

        chunks = chunk_text(content)
        category = file_path.stem.replace("_", " ").upper()

        print(f"  -> Processing '{file_path.name}' ({len(chunks)} chunks)")

        for chunk in chunks:
            formatted_fact = f"[{category} REFERENCE]: {chunk}"

            if save_memory(formatted_fact):
                total_chunks += 1

    print(f"Ingestion complete. Added {total_chunks} memory chunks.")


if __name__ == "__main__":
    ingest_documents()
