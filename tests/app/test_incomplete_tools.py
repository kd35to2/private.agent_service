from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from client import AgentClientError
from schema import ChatHistory, ChatMessage
from schema.errors import PUBLIC_ERROR_MESSAGES


def tool_request():
    return ChatMessage(
        type="ai",
        content="",
        tool_calls=[
            {"name": "Database_Search", "id": "search-1", "args": {"query": "leave"}},
            {"name": "Database_Search", "id": "search-2", "args": {"query": "vacation"}},
        ],
    )


def test_incomplete_history_does_not_crash(mock_agent_client):
    mock_agent_client.get_history.return_value = ChatHistory(messages=[tool_request()])
    app = AppTest.from_file("../../src/streamlit_app.py")
    app.query_params["thread_id"] = "unfinished-thread"
    app.run(timeout=10)
    assert not app.exception
    assert "未完成的工具调用" in app.warning[0].value


def test_truncated_stream_reports_missing_results(mock_agent_client):
    async def events():
        yield tool_request()
        yield ChatMessage(type="tool", content='{"results": [{}]}', tool_call_id="search-1")
        raise AgentClientError(PUBLIC_ERROR_MESSAGES["KNOWLEDGE_BASE_UNAVAILABLE"])

    mock_agent_client.astream = Mock(return_value=events())
    app = AppTest.from_file("../../src/streamlit_app.py").run(timeout=10)
    app.chat_input[0].set_value("Question").run(timeout=10)
    assert not app.exception
    assert app.error[0].value == PUBLIC_ERROR_MESSAGES["KNOWLEDGE_BASE_UNAVAILABLE"]
    assert not any(msg.content.startswith("Error:") for msg in app.session_state.messages)


def test_unexpected_failure_is_logged_without_frontend_traceback(mock_agent_client, caplog):
    async def events():
        yield tool_request()
        raise RuntimeError("PRIVATE_INTERNAL_DETAIL C:/server/secret.py")

    mock_agent_client.astream = Mock(return_value=events())
    app = AppTest.from_file("../../src/streamlit_app.py").run(timeout=10)
    app.chat_input[0].set_value("Question").run(timeout=10)
    assert not app.exception
    assert app.error[0].value == PUBLIC_ERROR_MESSAGES["AGENT_EXECUTION_FAILED"]
    assert "PRIVATE_INTERNAL_DETAIL" not in app.error[0].value
    assert "PRIVATE_INTERNAL_DETAIL" in caplog.text


def test_tool_results_can_be_interleaved_and_out_of_order(mock_agent_client):
    async def events():
        yield tool_request()
        yield "正在检索"
        yield ChatMessage(type="tool", content='{"results": [{}, {}]}', tool_call_id="search-2")
        yield ChatMessage(type="tool", content='{"results": [{}]}', tool_call_id="search-1")
        yield ChatMessage(type="ai", content="Final answer")

    mock_agent_client.astream = Mock(return_value=events())
    app = AppTest.from_file("../../src/streamlit_app.py").run(timeout=10)
    app.chat_input[0].set_value("Question").run(timeout=10)
    assert not app.exception
    assert not app.warning
    result = app.chat_message[1]
    assert result.status[0].markdown[-1].value == "检索到 1 个相关片段。"
    assert result.status[1].markdown[-1].value == "检索到 2 个相关片段。"
