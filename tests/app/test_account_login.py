from unittest.mock import AsyncMock

from streamlit.runtime.context import ContextProxy
from streamlit.testing.v1 import AppTest

from client import AgentClientError
from schema import ChatMessage


def test_account_mode_requires_sign_in(mock_agent_client, monkeypatch):
    monkeypatch.setenv("USER_AUTH_ENABLED", "true")
    monkeypatch.setattr(ContextProxy, "cookies", property(lambda _: {}))
    app = AppTest.from_file("../../src/streamlit_app.py").run(timeout=10)
    assert app.title[0].value == "登录后开始聊天"
    assert not app.chat_input
    assert not app.exception


def test_account_mode_uses_authenticated_id(mock_agent_client, monkeypatch):
    monkeypatch.setenv("USER_AUTH_ENABLED", "true")
    monkeypatch.setattr(
        ContextProxy, "cookies", property(lambda _: {"agent_session": "test-token"})
    )
    mock_agent_client.get_current_user.return_value = {"id": "account-123", "username": "alice"}
    mock_agent_client.ainvoke = AsyncMock(return_value=ChatMessage(type="ai", content="OK"))
    app = AppTest.from_file("../../src/streamlit_app.py")
    app.query_params["user_id"] = "spoofed-user"
    app.run(timeout=10)
    assert "user_id" not in app.query_params
    app.sidebar.toggle[0].set_value(False)
    app.chat_input[0].set_value("Hello").run(timeout=10)
    assert mock_agent_client.ainvoke.call_args.kwargs["user_id"] == "account-123"
    assert mock_agent_client.access_token == "test-token"
    assert not app.exception


def test_expired_account_session_blocks_chat(mock_agent_client, monkeypatch):
    monkeypatch.setenv("USER_AUTH_ENABLED", "true")
    monkeypatch.setattr(
        ContextProxy, "cookies", property(lambda _: {"agent_session": "expired-token"})
    )
    mock_agent_client.get_current_user.side_effect = AgentClientError("Expired")
    app = AppTest.from_file("../../src/streamlit_app.py").run(timeout=10)
    assert not app.chat_input
    assert "登录已过期" in app.warning[0].value
    assert not app.exception
