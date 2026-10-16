import json

import httpx
import pytest
from pydantic import SecretStr

from core.embeddings import create_embeddings, embedding_configuration_error
from core.settings import settings


def test_qwen_sends_raw_text_float_and_batches_at_ten(monkeypatch):
    monkeypatch.setattr(settings, "RAG_EMBEDDING_PROVIDER", "dashscope")
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", SecretStr("test-qwen-key"))
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("must-not-be-sent"))
    monkeypatch.setattr(settings, "RAG_EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setattr(settings, "RAG_EMBEDDING_BASE_URL", "https://qwen.example/v1")
    requests = []

    def respond(request):
        assert str(request.url) == "https://qwen.example/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-qwen-key"
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == "text-embedding-v4"
        assert body["encoding_format"] == "float"
        assert all(isinstance(text, str) for text in body["input"])
        assert len(body["input"]) <= 10
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [0.5, 0.25], "object": "embedding"}
                    for i in range(len(body["input"]))
                ],
                "model": "text-embedding-v4",
                "object": "list",
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    embeddings = create_embeddings()
    # Replace only the transport; exercise the actual LangChain/OpenAI request generation.
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        embeddings.client._client._client = client
        documents = [f"手册片段 {i}" for i in range(11)]
        assert len(embeddings.embed_documents(documents)) == 11
        assert embeddings.embed_query("一次能休几天？") == [0.5, 0.25]
    assert [len(body["input"]) for body in requests] == [10, 1, 1]
    assert requests[0]["input"] == documents[:10]
    assert requests[-1]["input"] == ["一次能休几天？"]


def test_qwen_requires_its_own_key(monkeypatch):
    monkeypatch.setattr(settings, "RAG_EMBEDDING_PROVIDER", "dashscope")
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("other-provider-key"))
    assert "DASHSCOPE_API_KEY" in embedding_configuration_error()
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        create_embeddings()
