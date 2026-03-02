"""Vector memory store: semantic search over user memories using ChromaDB."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import chromadb

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class VectorMemoryStore:
    """ChromaDB-backed semantic search over user memory entries.

    Uses ChromaDB's built-in embedding function (no additional model config needed).
    Documents are stored with id ``{user_id}:{key}`` and metadata ``user_id``
    for per-user filtering.
    """

    def __init__(
        self,
        data_dir: str | Path,
        collection_name: str = "openclaw_memory",
    ) -> None:
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb is required for vector memory. "
                "Install it with: pip install chromadb>=0.6.0"
            )

        persist_dir = Path(data_dir) / "vector_db"
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
        )

    def _doc_id(self, user_id: int, key: str) -> str:
        return f"{user_id}:{key}"

    def add(self, user_id: int, key: str, value: str) -> None:
        """Add or update a memory entry in the vector store."""
        doc_id = self._doc_id(user_id, key)
        self._collection.upsert(
            ids=[doc_id],
            documents=[value],
            metadatas=[{"user_id": user_id, "key": key}],
        )

    def remove(self, user_id: int, key: str) -> None:
        """Remove a memory entry from the vector store."""
        doc_id = self._doc_id(user_id, key)
        try:
            self._collection.delete(ids=[doc_id])
        except Exception:
            logger.debug("Vector entry not found for deletion: %s", doc_id)

    def search(
        self,
        user_id: int,
        query: str,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for similar memories for a specific user.

        Returns a list of dicts with ``key``, ``value``, and ``distance``.
        """
        results = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"user_id": user_id},
        )

        entries: list[dict[str, Any]] = []
        if results["documents"] and results["metadatas"] and results["distances"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results["distances"][0]

            for doc, meta, dist in zip(docs, metas, dists):
                entries.append({
                    "key": meta.get("key", ""),
                    "value": doc,
                    "distance": round(dist, 4),
                })

        return entries
