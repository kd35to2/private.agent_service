import pytest

from rag.models import DocumentVersion, KnowledgeDocument
from schema.errors import AgentServiceError


@pytest.mark.asyncio
async def test_duplicate_update_failure_and_restart_preserve_active_version(knowledge):
    service, embeddings, index = knowledge
    old = "项目 AP2609-3074 的审核状态为待处理。".encode()
    created = await service.ingest("alice", "项目.txt", old)
    duplicate = await service.ingest("alice", "另一个名字.txt", old)
    assert duplicate["duplicate"]
    assert duplicate["document_id"] == created["document_id"]
    assert embeddings.calls == 1
    embeddings.fail = True
    with pytest.raises(AgentServiceError, match="旧版本仍保留"):
        await service.ingest(
            "alice", "项目.txt", "新版内容，生成失败".encode(), created["document_id"]
        )
    chunks = await service.chunks("alice", created["document_id"])
    assert chunks["chunks"][0]["text"] == old.decode()
    async with service.database.sessions() as session:
        doc = await session.get(KnowledgeDocument, created["document_id"])
        active = doc.active_version_id
        version = DocumentVersion(
            id="interrupted",
            document_id=doc.id,
            number=3,
            content_hash="x" * 64,
            content=b"test",
            embedding_signature="dashscope:text-embedding-v4",
        )
        session.add(version)
        doc.pending_version_id, doc.status = version.id, "processing"
        await session.commit()
    await service.recover()
    async with service.database.sessions() as session:
        doc = await session.get(KnowledgeDocument, created["document_id"])
        assert doc.active_version_id == active
        assert doc.pending_version_id is None
        assert (await session.get(DocumentVersion, "interrupted")).status == "failed"
    embeddings.fail = False
    assert (await service.search("alice", "AP2609-3074")).results[0].text == old.decode()


@pytest.mark.asyncio
async def test_private_visibility_update_and_logical_delete_even_if_cleanup_fails(knowledge):
    service, _, index = knowledge
    doc = await service.ingest("alice", "资料.txt", "项目 AP2609-3074 待处理".encode())
    doc_id = doc["document_id"]
    assert await service.list_documents("bob") == []
    assert not (await service.search("bob", "AP2609-3074")).results
    with pytest.raises(AgentServiceError) as error:
        await service.chunks("bob", doc_id)
    assert error.value.status_code == 404
    old_chunk = (await service.chunks("alice", doc_id))["chunks"][0]["id"]
    index.fail_cleanup = True
    await service.ingest("alice", "资料.txt", "项目 AP2609-3074 已批准".encode(), doc_id)
    result = await service.search("alice", "AP2609-3074")
    assert all("已批准" in row.text for row in result.results)
    assert all(row.chunk_id != old_chunk for row in result.results)
    await service.delete("alice", doc_id)
    assert index.records  # Physical stale records deliberately remain.
    assert not (await service.search("alice", "AP2609-3074")).results
    with pytest.raises(AgentServiceError):
        await service.chunk("alice", doc_id, old_chunk)


@pytest.mark.asyncio
async def test_same_filename_requires_explicit_update_and_owner_cannot_be_changed(knowledge):
    service, _, _ = knowledge
    doc = await service.ingest("alice", "资料.txt", b"original content")
    with pytest.raises(AgentServiceError) as error:
        await service.ingest("alice", "资料.txt", b"different content")
    assert error.value.status_code == 409
    for action in [
        lambda: service.ingest("bob", "资料.txt", b"replacement", doc["document_id"]),
        lambda: service.reindex("bob", doc["document_id"]),
        lambda: service.delete("bob", doc["document_id"]),
    ]:
        with pytest.raises(AgentServiceError) as error:
            await action()
        assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_reindex_creates_version_without_deleting_whole_library(knowledge):
    service, _, _ = knowledge
    first = await service.ingest("alice", "一.txt", b"first information")
    second = await service.ingest("alice", "二.txt", b"second information")
    result = await service.reindex("alice", first["document_id"])
    assert result["version"] == 2
    assert len(await service.list_documents("alice")) == 2
    assert (await service.chunks("alice", second["document_id"]))["chunks"]


@pytest.mark.asyncio
async def test_new_upload_failure_is_recorded_and_retryable(knowledge):
    service, embeddings, _ = knowledge
    embeddings.fail = True
    with pytest.raises(AgentServiceError):
        await service.ingest("alice", "重试.txt", b"some knowledge")
    rows = await service.list_documents("alice")
    assert rows[0]["status"] == "failed"
    assert rows[0]["chunk_count"] == 0
    embeddings.fail = False
    await service.reindex("alice", rows[0]["id"])
    assert (await service.list_documents("alice"))[0]["status"] == "ready"
