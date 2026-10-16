from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage

from agents import DEFAULT_AGENT, get_agent, get_all_agent_info
from agents.rag_assistant import answer, retrieve
from rag.citations import validate_answer
from rag.schemas import Evidence, SearchResult


def evidence():
    return Evidence(
        citation=1,
        document_id="doc",
        document_name="方案.docx",
        version=1,
        version_id="version",
        chunk_id="chunk",
        chunk_index=1,
        start_index=0,
        text="项目 AP2609-3074 待处理。",
    )


def test_only_rag_is_registered():
    assert DEFAULT_AGENT == "rag-assistant"
    assert [a.key for a in get_all_agent_info()] == [DEFAULT_AGENT]
    with pytest.raises(HTTPException) as error:
        get_agent("research-assistant")
    assert error.value.status_code == 404


def test_citations_are_validated_and_model_links_not_trusted():
    result = SearchResult(query="status", results=[evidence()])
    text, citations = validate_answer("项目待处理。[1]", result)
    assert text == "项目待处理。[1]"
    assert citations[0]["chunk_id"] == "chunk"
    for invalid in ["编造答案。[99]", "没有引用", "[文件](https://fake.invalid/secret)"]:
        text, _ = validate_answer(invalid, result)
        assert "未形成可核查引用" in text
        assert "fake.invalid" not in text


@pytest.mark.asyncio
async def test_empty_knowledge_does_not_call_model(monkeypatch):
    model = AsyncMock()
    monkeypatch.setattr("agents.rag_assistant.get_model", model)
    output = await answer(
        {
            "messages": [HumanMessage(content="你好")],
            "evidence": SearchResult(query="你好").model_dump(),
        },
        {"configurable": {}},
    )
    assert "未找到足够资料" in output["messages"][0].content
    model.assert_not_called()


@pytest.mark.asyncio
async def test_retrieval_precedes_answer_and_evidence_reaches_client(monkeypatch):
    result = SearchResult(query="status", results=[evidence()])
    search = AsyncMock(return_value=result.model_dump_json())
    monkeypatch.setattr("agents.rag_assistant.database_search", Mock(ainvoke=search))
    config = {"configurable": {"user_id": "verified-owner"}}
    update = await retrieve({"messages": [HumanMessage(content="status")]}, config)
    search.assert_awaited_once_with({"query": "status"}, config=config)
    model = AsyncMock()
    model.ainvoke.return_value = AIMessage(content="项目待处理。[1]")
    monkeypatch.setattr("agents.rag_assistant.get_model", lambda _: model)
    output = await answer(
        {
            "messages": [HumanMessage(content="status"), *update["messages"]],
            "evidence": update["evidence"],
        },
        config,
    )
    assert (
        output["messages"][0].additional_kwargs["rag"]["citations"][0]["document_name"]
        == "方案.docx"
    )
    assert "skip_stream" in model.ainvoke.call_args.args[1]["tags"]
    assert model.ainvoke.call_args.args[1]["metadata"]["emit-messages"] is False
