import json

from langchain_core.messages import AIMessage

from core import settings
from schema.errors import PUBLIC_ERROR_MESSAGES, AgentServiceError


def test_unconfigured_rag_returns_safe_503(test_client, mock_agent, monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(settings, "USER_AUTH_ENABLED", False)
    monkeypatch.setattr(settings, "AUTH_SECRET", None)

    def unavailable():
        raise AgentServiceError(
            "KNOWLEDGE_BASE_UNAVAILABLE", detail="OPENAI_API_KEY private path chroma_db"
        )

    monkeypatch.setattr("service.service.ensure_rag_available", unavailable)
    for path in ["/rag-assistant/invoke", "/rag-assistant/stream"]:
        response = test_client.post(path, json={"message": "How many vacation days?"})
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "code": "KNOWLEDGE_BASE_UNAVAILABLE",
            "message": PUBLIC_ERROR_MESSAGES["KNOWLEDGE_BASE_UNAVAILABLE"],
        }
        for internal in ["OPENAI_API_KEY", "chroma_db", "create_chroma_db.py", "Traceback"]:
            assert internal not in response.text
    assert "OPENAI_API_KEY" in caplog.text
    mock_agent.ainvoke.assert_not_awaited()
    mock_agent.aget_state.assert_not_awaited()


def test_stream_failure_is_an_error_event_not_a_chat_message(test_client, mock_agent, monkeypatch):
    monkeypatch.setattr(settings, "USER_AUTH_ENABLED", False)
    monkeypatch.setattr(settings, "AUTH_SECRET", None)

    async def events(**kwargs):
        yield (
            "updates",
            {
                "model": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "Database_Search",
                                    "id": "search-1",
                                    "args": {"query": "leave"},
                                }
                            ],
                        )
                    ]
                }
            },
        )
        raise AgentServiceError(
            "KNOWLEDGE_BASE_UNAVAILABLE", detail="PRIVATE_KEY C:/private/file.py"
        )

    mock_agent.astream = events
    response = test_client.post("/test-agent/stream", json={"message": "Question"})
    assert response.status_code == 200
    data = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line[6:] != "[DONE]"
    ]
    error = next(item for item in data if item["type"] == "error")
    assert error == {
        "type": "error",
        "code": "KNOWLEDGE_BASE_UNAVAILABLE",
        "message": PUBLIC_ERROR_MESSAGES["KNOWLEDGE_BASE_UNAVAILABLE"],
    }
    assert "PRIVATE_KEY" not in response.text
    assert "C:/private" not in response.text
    assert "data: [DONE]" in response.text
