import json

import httpx
import pytest

from client.client import AgentClient, AgentClientError, public_http_error
from schema.errors import PUBLIC_ERROR_MESSAGES


def test_http_diagnostics_are_not_exposed():
    response = httpx.Response(
        503,
        request=httpx.Request("POST", "http://private-host/secret"),
        json={
            "detail": {
                "code": "KNOWLEDGE_BASE_UNAVAILABLE",
                "message": "PRIVATE_SQL OPENAI_API_KEY",
            }
        },
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        response.raise_for_status()
    error = public_http_error(exc.value)
    assert str(error) == PUBLIC_ERROR_MESSAGES["KNOWLEDGE_BASE_UNAVAILABLE"]
    assert "PRIVATE_SQL" not in str(error)
    assert "private-host" not in str(error)


def test_stream_errors_are_not_converted_into_ai_messages():
    client = AgentClient(get_info=False)
    line = "data: " + json.dumps({"type": "error", "content": "PRIVATE_INTERNAL_TRACE"})
    with pytest.raises(AgentClientError) as exc:
        client._parse_stream_line(line)
    assert str(exc.value) == PUBLIC_ERROR_MESSAGES["AGENT_EXECUTION_FAILED"]
    assert "PRIVATE_INTERNAL_TRACE" not in str(exc.value)
