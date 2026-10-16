import pytest

from rag.retrieval import identifiers, tokenize


def test_identifier_is_preserved_by_chinese_tokenizer():
    assert "ap2609-3074" in tokenize("帮我查 AP2609-3074 的状态")
    assert identifiers("AP2609-3074") == {"ap2609-3074"}


@pytest.mark.asyncio
async def test_exact_identifier_does_not_return_similar_number(knowledge):
    service, _, _ = knowledge
    await service.ingest("alice", "相似编号.txt", "项目 AP2609-3075 已完成。".encode())
    await service.ingest("alice", "正确编号.txt", "项目 AP2609-3074 待处理。".encode())
    result = await service.search("alice", "AP2609-3074 的状态？")
    assert result.results
    assert all("AP2609-3074" in row.text for row in result.results)
    assert not (await service.search("alice", "AP2609-9999 状态")).results


@pytest.mark.asyncio
async def test_rerank_and_degradation_are_explicit(knowledge):
    service, embeddings, _ = knowledge
    await service.ingest("alice", "年假.txt", "员工每年享有15天年假。".encode())
    await service.ingest("alice", "假期流程.txt", "年假需要提前申请。".encode())

    async def reverse(query, texts):
        return [(i, 0.95 - j * 0.1) for j, i in enumerate(reversed(range(len(texts))))]

    service.reranker = reverse
    result = await service.search("alice", "年假")
    assert result.results[0].document_name == "假期流程.txt"
    assert result.results[0].rerank_score == 0.95

    async def unavailable(*args):
        raise RuntimeError("PRIVATE_RERANK_FAILURE")

    service.reranker = unavailable
    embeddings.fail = True
    result = await service.search("alice", "年假")
    assert result.degraded
    assert len(result.notices) == 2
    assert result.results
    assert "PRIVATE" not in result.model_dump_json()
