from pathlib import Path
from threading import RLock
from typing import cast

import chromadb
from chromadb.api.types import Metadata, Where


class ChromaIndex:
    """One process owns this local index. PostgreSQL decides which versions are visible."""

    def __init__(self, path: str):
        self.path = str(Path(path).resolve())
        self._lock = RLock()
        self._collection = None

    def collection(self):
        with self._lock:
            if self._collection is None:
                client = chromadb.PersistentClient(path=self.path)
                self._collection = client.get_or_create_collection("kb_chunks_v1")
            return self._collection

    def upsert(self, owner: str, document: str, version: str, chunks: list, vectors: list) -> None:
        with self._lock:
            for offset in range(0, len(chunks), 100):
                batch = chunks[offset : offset + 100]
                metadata: list[Metadata] = [
                    {"owner_id": owner, "document_id": document, "version_id": version}
                    for _ in batch
                ]
                self.collection().upsert(
                    ids=[c.id for c in batch],
                    embeddings=vectors[offset : offset + 100],
                    documents=[c.text for c in batch],
                    metadatas=metadata,
                )

    def search(self, owner: str, versions: list[str], vector: list[float], k: int) -> list[str]:
        if not versions:
            return []
        with self._lock:
            where = cast(
                Where, {"$and": [{"owner_id": owner}, {"version_id": {"$in": list(versions)}}]}
            )
            result = self.collection().query(
                query_embeddings=[vector],
                n_results=k,
                where=where,
                include=[],
            )
            return result["ids"][0]

    def delete_version(self, owner: str, version: str) -> None:
        with self._lock:
            self.collection().delete(where={"$and": [{"owner_id": owner}, {"version_id": version}]})
