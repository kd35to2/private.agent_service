import os

import httpx
import pytest


@pytest.mark.docker
def test_rag_service_registry_and_private_documents():
    """Requires a running service, no paid model calls or anonymous knowledge access."""
    base = os.getenv("AGENT_URL", "http://127.0.0.1:8081")
    with httpx.Client(base_url=base, trust_env=False) as client:
        assert client.get("/health").status_code == 200
        info = client.get("/info").json()
        assert info["default_agent"] == "rag-assistant"
        assert [item["key"] for item in info["agents"]] == ["rag-assistant"]
        assert client.get("/knowledge/documents").status_code == 401
