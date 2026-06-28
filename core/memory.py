from __future__ import annotations

import uuid
from pathlib import Path

import chromadb

from config import LOCAL_DATA_DIR


DB_PATH = LOCAL_DATA_DIR / "vector_db"
collection = None


def init_db() -> None:
    global collection

    if collection is not None:
        return

    print("⏳ Initializing Vector Database...")
    DB_PATH.mkdir(parents=True, exist_ok=True)

    chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = chroma_client.get_or_create_collection(
        name="avens_cognitive_vault"
    )


def save_memory(fact: str) -> bool:
    init_db()

    normalized_fact = fact.strip()
    if not normalized_fact:
        return False

    try:
        collection.add(
            documents=[normalized_fact],
            ids=[str(uuid.uuid4())],
        )
        print(f"🧠 [Vector Index Locked]: {normalized_fact}")
        return True

    except Exception as error:
        print(f"⚠️ Vector Memory Write Failure: {error}")
        return False


def load_memory(current_query: str | None = None, n_results: int = 4) -> str:
    init_db()

    if not current_query or not current_query.strip():
        return "- No specific past context retrieved for this turn."

    try:
        results = collection.query(
            query_texts=[current_query],
            n_results=n_results,
        )
        documents = results.get("documents", [[]])[0]

        if not documents:
            return "- No relevant past memories found for this topic."

        return "\n".join(f"- {document}" for document in documents)

    except Exception as error:
        print(f"⚠️ Vector Retrieval Anomaly: {error}")
        return "- Long-term memory system offline."
