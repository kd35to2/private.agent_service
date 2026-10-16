import asyncio
import hashlib
import logging
from collections.abc import Callable

from sqlalchemy import func, select

from accounts.database import AccountDatabase
from core import settings
from core.embeddings import create_embeddings
from rag.models import DocumentVersion, KnowledgeChunk, KnowledgeDocument, new_id
from rag.rerank import rerank
from rag.retrieval import fuse, identifiers, keyword_search
from rag.schemas import Evidence, SearchResult
from rag.splitting import chunk_id, safe_name, split_content
from rag.stores import ChromaIndex
from schema.errors import AgentServiceError

logger = logging.getLogger(__name__)


def failure(code: str, status: int = 503, detail: str = "") -> AgentServiceError:
    return AgentServiceError(code, status_code=status, detail=detail or code)


def embedding_signature() -> str:
    provider = settings.RAG_EMBEDDING_PROVIDER
    model = settings.RAG_EMBEDDING_MODEL or (
        "text-embedding-v4" if provider == "dashscope" else "text-embedding-3-small"
    )
    return f"{provider}:{model}"


class KnowledgeBase:
    def __init__(
        self,
        database: AccountDatabase,
        index=None,
        embedding_factory: Callable = create_embeddings,
        reranker: Callable = rerank,
    ):
        self.database = database
        self.index = index or ChromaIndex(settings.RAG_CHROMA_PATH)
        self.embedding_factory = embedding_factory
        self.reranker = reranker
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, owner: str) -> asyncio.Lock:
        return self._locks.setdefault(owner, asyncio.Lock())

    async def owned(
        self, session, owner: str, document_id: str, *, locked=False
    ) -> KnowledgeDocument:
        query = select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.owner_id == owner,
            KnowledgeDocument.deleted.is_(False),
        )
        if locked:
            query = query.with_for_update()
        doc = await session.scalar(query)
        if doc is None:
            raise failure("DOCUMENT_NOT_FOUND", 404)
        return doc

    async def recover(self) -> None:
        """A stopped request cannot finish after a process restart. Keep its old active version."""
        async with self.database.sessions() as session:
            docs = (
                await session.scalars(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.pending_version_id.is_not(None)
                    )
                )
            ).all()
            for doc in docs:
                version = await session.get(DocumentVersion, doc.pending_version_id)
                if version:
                    version.status = "failed"
                    version.error = "Processing interrupted; retry indexing."
                doc.pending_version_id = None
                doc.status = "failed"
            await session.commit()

        # Retry deferred cleanup from interrupted uploads, old versions and deleted documents.
        async with self.database.sessions() as session:
            versions = (
                await session.execute(
                    select(DocumentVersion.id, KnowledgeDocument.owner_id)
                    .join(KnowledgeDocument, DocumentVersion.document_id == KnowledgeDocument.id)
                    .where(
                        (KnowledgeDocument.active_version_id.is_(None))
                        | (DocumentVersion.id != KnowledgeDocument.active_version_id)
                        | KnowledgeDocument.deleted.is_(True)
                    )
                )
            ).all()
        for version_id, owner in versions:
            await self.cleanup(owner, version_id)

    async def list_documents(self, owner: str) -> list[dict]:
        async with self.database.sessions() as session:
            docs = (
                await session.scalars(
                    select(KnowledgeDocument)
                    .where(
                        KnowledgeDocument.owner_id == owner, KnowledgeDocument.deleted.is_(False)
                    )
                    .order_by(KnowledgeDocument.created_at.desc())
                )
            ).all()
            output = []
            for doc in docs:
                versions = (
                    await session.scalars(
                        select(DocumentVersion)
                        .where(DocumentVersion.document_id == doc.id)
                        .order_by(DocumentVersion.number.desc())
                    )
                ).all()
                active = next((v for v in versions if v.id == doc.active_version_id), None)
                count = await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeChunk)
                    .where(KnowledgeChunk.version_id == doc.active_version_id)
                )
                output.append(
                    {
                        "id": doc.id,
                        "name": doc.name,
                        "status": doc.status,
                        "version": active.number if active else None,
                        "chunk_count": count or 0,
                        "versions": [
                            {
                                "id": v.id,
                                "number": v.number,
                                "status": v.status,
                                "error": "文档处理失败，可重新索引。" if v.error else None,
                            }
                            for v in versions
                        ],
                    }
                )
            return output

    async def ingest(
        self,
        owner: str,
        name: str,
        content: bytes,
        document_id: str | None = None,
        *,
        force=False,
        inherited=None,
    ) -> dict:
        try:
            name = safe_name(name)
            if not content or len(content) > settings.RAG_MAX_UPLOAD_MB * 1024 * 1024:
                raise ValueError("Invalid upload size")
            if settings.RAG_CHUNK_OVERLAP >= settings.RAG_CHUNK_SIZE:
                raise ValueError("Overlap must be smaller than chunk size")
        except ValueError as error:
            raise failure("DOCUMENT_INVALID", 422, str(error)) from error
        digest = hashlib.sha256(content).hexdigest()
        async with self.lock(owner):
            async with self.database.sessions() as session:
                if document_id:
                    doc = await self.owned(session, owner, document_id, locked=True)
                else:
                    # Identical active content is idempotent even if the filename changed.
                    duplicate = await session.scalar(
                        select(KnowledgeDocument)
                        .join(
                            DocumentVersion,
                            KnowledgeDocument.active_version_id == DocumentVersion.id,
                        )
                        .where(
                            KnowledgeDocument.owner_id == owner,
                            KnowledgeDocument.deleted.is_(False),
                            DocumentVersion.content_hash == digest,
                        )
                    )
                    if duplicate and not force:
                        return {"document_id": duplicate.id, "duplicate": True}
                    doc = await session.scalar(
                        select(KnowledgeDocument)
                        .where(
                            KnowledgeDocument.owner_id == owner,
                            KnowledgeDocument.name == name,
                            KnowledgeDocument.deleted.is_(False),
                        )
                        .with_for_update()
                    )
                    if doc and doc.active_version_id:
                        raise failure("DOCUMENT_CONFLICT", 409)
                    if doc is None:
                        doc = KnowledgeDocument(id=new_id(), owner_id=owner, name=name)
                        session.add(doc)
                        await session.flush()
                if doc.pending_version_id:
                    raise failure("DOCUMENT_BUSY", 409)
                active = (
                    await session.get(DocumentVersion, doc.active_version_id)
                    if doc.active_version_id
                    else None
                )
                if (
                    active
                    and not force
                    and active.content_hash == digest
                    and active.embedding_signature == embedding_signature()
                ):
                    return {"document_id": doc.id, "duplicate": True}
                number = (
                    await session.scalar(
                        select(func.max(DocumentVersion.number)).where(
                            DocumentVersion.document_id == doc.id
                        )
                    )
                    or 0
                ) + 1
                version = DocumentVersion(
                    id=new_id(),
                    document_id=doc.id,
                    number=number,
                    content_hash=digest,
                    content=content,
                    embedding_signature=embedding_signature(),
                    chunk_size=settings.RAG_CHUNK_SIZE,
                    chunk_overlap=settings.RAG_CHUNK_OVERLAP,
                )
                session.add(version)
                doc.pending_version_id, doc.status = version.id, "processing"
                doc_id, version_id, old_version = doc.id, version.id, doc.active_version_id
                await session.commit()
            try:
                if inherited is not None:
                    parts, vectors = inherited
                else:
                    parts = await asyncio.to_thread(
                        split_content,
                        name,
                        content,
                        settings.RAG_CHUNK_SIZE,
                        settings.RAG_CHUNK_OVERLAP,
                    )
                    embedder = self.embedding_factory()
                    vectors = await asyncio.to_thread(
                        embedder.embed_documents, [p.page_content for p in parts]
                    )
                if len(parts) != len(vectors) or not parts:
                    raise ValueError("Invalid embedding count")
                chunks = [
                    KnowledgeChunk(
                        id=chunk_id(version_id, i + 1, p.page_content),
                        version_id=version_id,
                        ordinal=i + 1,
                        text=p.page_content,
                        page=(int(p.metadata["page"]) + 1) if "page" in p.metadata else None,
                        start_index=int(p.metadata.get("start_index", -1)),
                    )
                    for i, p in enumerate(parts)
                ]
                await asyncio.to_thread(
                    self.index.upsert, owner, doc_id, version_id, chunks, vectors
                )
                async with self.database.sessions() as session:
                    doc = await self.owned(session, owner, doc_id, locked=True)
                    if doc.pending_version_id != version_id:
                        raise ValueError("Document version changed while indexing")
                    session.add_all(chunks)
                    version = await session.get(DocumentVersion, version_id)
                    if version is None:
                        raise ValueError("Pending version no longer exists")
                    version.status = "ready"
                    doc.active_version_id, doc.pending_version_id, doc.status = (
                        version_id,
                        None,
                        "ready",
                    )
                    doc.name = name
                    await session.commit()
            except (Exception, asyncio.CancelledError) as error:
                logger.exception("Knowledge document processing failed: %s", doc_id)
                async with self.database.sessions() as session:
                    version = await session.get(DocumentVersion, version_id)
                    if version is not None:
                        version.status, version.error = (
                            "failed",
                            "Processing failed; see server logs.",
                        )
                    doc = await session.get(KnowledgeDocument, doc_id)
                    if doc is not None and doc.pending_version_id == version_id:
                        doc.pending_version_id, doc.status = None, "failed"
                    await session.commit()
                await self.cleanup(owner, version_id)
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise failure(
                    "DOCUMENT_PROCESSING_FAILED", detail=f"Document {doc_id} indexing failed"
                ) from error
            if old_version:
                await self.cleanup(owner, old_version)
            return {
                "document_id": doc_id,
                "version": number,
                "chunk_count": len(chunks),
                "duplicate": False,
            }

    async def cleanup(self, owner: str, version_id: str) -> None:
        try:
            await asyncio.to_thread(self.index.delete_version, owner, version_id)
        except Exception:
            # Failed/old versions are excluded by the SQL active-version allowlist.
            logger.exception("Deferred index cleanup needed for version %s", version_id)

    async def reindex(self, owner: str, document_id: str) -> dict:
        async with self.database.sessions() as session:
            doc = await self.owned(session, owner, document_id)
            latest = await session.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc.id)
                .order_by(DocumentVersion.number.desc())
                .limit(1)
            )
            if latest is None:
                raise failure("DOCUMENT_NOT_FOUND", 404)
            name, content = doc.name, latest.content
        return await self.ingest(owner, name, content, document_id, force=True)

    async def delete(self, owner: str, document_id: str) -> None:
        async with self.lock(owner):
            async with self.database.sessions() as session:
                doc = await self.owned(session, owner, document_id, locked=True)
                doc.deleted, doc.active_version_id, doc.status = True, None, "deleted"
                versions = (
                    await session.scalars(
                        select(DocumentVersion.id).where(DocumentVersion.document_id == doc.id)
                    )
                ).all()
                await session.commit()
            for version_id in versions:
                await self.cleanup(owner, version_id)

    async def chunks(self, owner: str, document_id: str, offset=0, limit=20) -> dict:
        async with self.database.sessions() as session:
            doc = await self.owned(session, owner, document_id)
            rows = (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.version_id == doc.active_version_id)
                    .order_by(KnowledgeChunk.ordinal)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return {
                "document_id": doc.id,
                "name": doc.name,
                "chunks": [
                    {
                        "id": r.id,
                        "index": r.ordinal,
                        "page": r.page,
                        "start_index": r.start_index,
                        "characters": len(r.text),
                        "text": r.text,
                    }
                    for r in rows
                ],
            }

    async def chunk(self, owner: str, document_id: str, chunk_id: str) -> dict:
        async with self.database.sessions() as session:
            doc = await self.owned(session, owner, document_id)
            row = (
                await session.execute(
                    select(KnowledgeChunk, DocumentVersion)
                    .join(DocumentVersion, KnowledgeChunk.version_id == DocumentVersion.id)
                    .where(KnowledgeChunk.id == chunk_id, DocumentVersion.document_id == doc.id)
                )
            ).first()
            if row is None:
                raise failure("DOCUMENT_NOT_FOUND", 404)
            chunk, version = row
            return {
                "document_id": doc.id,
                "document_name": doc.name,
                "version": version.number,
                "chunk_id": chunk.id,
                "chunk_index": chunk.ordinal,
                "page": chunk.page,
                "start_index": chunk.start_index,
                "text": chunk.text,
                "current": version.id == doc.active_version_id,
            }

    async def active_rows(self, owner: str) -> tuple[list[Evidence], dict[str, str]]:
        async with self.database.sessions() as session:
            rows = (
                await session.execute(
                    select(KnowledgeChunk, DocumentVersion, KnowledgeDocument)
                    .join(DocumentVersion, KnowledgeChunk.version_id == DocumentVersion.id)
                    .join(
                        KnowledgeDocument, KnowledgeDocument.active_version_id == DocumentVersion.id
                    )
                    .where(
                        KnowledgeDocument.owner_id == owner,
                        KnowledgeDocument.deleted.is_(False),
                        DocumentVersion.status == "ready",
                    )
                )
            ).all()
            evidence = [
                Evidence(
                    document_id=d.id,
                    document_name=d.name,
                    version=v.number,
                    version_id=v.id,
                    chunk_id=c.id,
                    chunk_index=c.ordinal,
                    page=c.page,
                    start_index=c.start_index,
                    text=c.text,
                    source_url=f"/knowledge/documents/{d.id}/chunks/{c.id}",
                )
                for c, v, d in rows
            ]
            return evidence, {v.id: v.embedding_signature for _, v, _ in rows}

    async def search(self, owner: str, query: str, limit: int | None = None) -> SearchResult:
        rows, versions = await self.active_rows(owner)
        response = SearchResult(query=query)
        if not rows:
            return response
        by_id = {row.chunk_id: row for row in rows}
        lexical = await asyncio.to_thread(keyword_search, query, rows, settings.RAG_KEYWORD_K)
        semantic = []
        compatible = [v for v, signature in versions.items() if signature == embedding_signature()]
        if len(compatible) != len(versions):
            response.degraded = True
            response.notices.append("部分文档嵌入模型已变更，请重新索引；这些文档暂用关键词检索。")
        if compatible:
            try:
                embedder = self.embedding_factory()
                vector = await asyncio.to_thread(embedder.embed_query, query)
                semantic = await asyncio.to_thread(
                    self.index.search, owner, compatible, vector, settings.RAG_VECTOR_K
                )
            except Exception:
                logger.exception("Vector recall unavailable; using keyword retrieval")
                response.degraded = True
                response.notices.append("向量检索暂不可用，本次使用关键词检索。")
        ranked = fuse(semantic, lexical)
        candidates = []
        required = identifiers(query)
        for key, score in ranked:
            row = by_id.get(key)
            if row is None or (required and not required.issubset(identifiers(row.text))):
                continue
            candidates.append(row.model_copy(update={"fusion_score": score}))
        # Explicit identifiers can otherwise be crowded out before lexical top-k.
        if required:
            seen = {row.chunk_id for row in candidates}
            candidates.extend(
                r for r in rows if r.chunk_id not in seen and required.issubset(identifiers(r.text))
            )
            candidates = candidates[: settings.RAG_VECTOR_K + settings.RAG_KEYWORD_K]
        if not candidates:
            return response
        if settings.RAG_RERANK_ENABLED:
            try:
                ordering = await self.reranker(query, [r.text for r in candidates])
                candidates = [
                    candidates[i].model_copy(update={"rerank_score": score})
                    for i, score in ordering
                    if score >= settings.RAG_MIN_RERANK_SCORE
                ]
            except Exception:
                logger.exception("Rerank unavailable; using reciprocal-rank fusion")
                response.degraded = True
                response.notices.append("重排暂不可用，本次使用混合召回排序。")
        # Re-check visibility after remote calls, so a deleted/replaced version cannot leak.
        current, _ = await self.active_rows(owner)
        allowed = {r.chunk_id for r in current}
        candidates = [r for r in candidates if r.chunk_id in allowed]
        seen_text = set()
        for candidate in candidates:
            fingerprint = hashlib.sha256(candidate.text.encode()).hexdigest()
            if fingerprint in seen_text:
                continue
            seen_text.add(fingerprint)
            candidate.citation = len(response.results) + 1
            response.results.append(candidate)
            if len(response.results) >= (limit or settings.RAG_TOP_K):
                break
        return response
