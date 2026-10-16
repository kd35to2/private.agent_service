"""Explicit-owner administrative ingestion/migration; never deletes a whole index."""

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from accounts.database import create_account_database  # noqa: E402
from accounts.models import User  # noqa: E402
from core import settings  # noqa: E402
from rag.documents import KnowledgeBase  # noqa: E402


async def run(args) -> None:
    database = create_account_database()
    try:
        await database.setup()
        async with database.sessions() as session:
            owner = await session.scalar(select(User).where(User.username == args.owner))
            if owner is None:
                raise ValueError("Owner does not exist. Register the intended account first.")
            owner_id = owner.id
        service = KnowledgeBase(database)
        if args.migrate_existing:
            import chromadb
            from langchain_core.documents import Document

            index_path = Path(settings.RAG_CHROMA_PATH).resolve()
            backup = ROOT / ".local" / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
            backup.mkdir(parents=True)
            shutil.copytree(index_path, backup / "chroma_db")
            legacy = chromadb.PersistentClient(path=str(index_path)).get_collection("langchain")
            records = legacy.get(include=["documents", "metadatas", "embeddings"])
            groups: dict[str, list[int]] = {}
            for index, metadata in enumerate(records["metadatas"]):
                groups.setdefault(metadata["source"], []).append(index)
            (backup / "migration.json").write_text(
                json.dumps(
                    {
                        "owner": args.owner,
                        "owner_id": owner_id,
                        "source_records": len(records["ids"]),
                        "sources": list(groups),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            for source, indexes in groups.items():
                path = (ROOT / source).resolve()
                if not path.is_relative_to(ROOT / "data"):
                    raise ValueError(
                        "Legacy source must be inside this repository's data directory"
                    )
                content = path.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                if any(
                    records["metadatas"][i].get("source_sha256", digest) != digest for i in indexes
                ):
                    raise ValueError("Source changed since indexing; do not migrate stale vectors")
                indexes.sort(
                    key=lambda i: (
                        records["metadatas"][i].get("chunk_index", 0),
                        records["metadatas"][i].get("page", 0),
                        records["metadatas"][i].get("start_index", 0),
                    )
                )
                parts = [
                    Document(page_content=records["documents"][i], metadata=records["metadatas"][i])
                    for i in indexes
                ]
                vectors = [records["embeddings"][i].tolist() for i in indexes]
                result = await service.ingest(
                    owner_id, path.name, content, inherited=(parts, vectors)
                )
                print(json.dumps({"file": path.name, **result}, ensure_ascii=True), flush=True)
            print("Legacy collection retained as an archive. New searches use kb_chunks_v1 only.")
        else:
            files = [Path(args.file).resolve()] if args.file else sorted((ROOT / "data").iterdir())
            for path in files:
                if path.is_file() and path.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}:
                    result = await service.ingest(owner_id, path.name, path.read_bytes())
                    print(json.dumps({"file": path.name, **result}, ensure_ascii=True), flush=True)
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--owner", required=True, help="Existing account username; knowledge remains private to it"
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--file", help="Import one file; otherwise imports supported files from data/"
    )
    actions.add_argument(
        "--migrate-existing",
        action="store_true",
        help="Back up and import legacy vectors without embedding API calls",
    )
    asyncio.run(
        run(parser.parse_args()),
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None,
    )


if __name__ == "__main__":
    main()
