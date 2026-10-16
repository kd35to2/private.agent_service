from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest
from streamlit.testing.v1 import AppTest

from client import AgentClientError
from schema import ChatHistory, ChatMessage, ThreadSummary, UserThreads
from schema.models import OpenAIModelName


def test_app_simple_non_streaming(mock_agent_client):
    """Test the full app - happy path"""
    at = AppTest.from_file("../../src/streamlit_app.py").run()

    WELCOME_START = "你好，我是你的知识库助手。"
    PROMPT = "Know any jokes?"
    RESPONSE = "Sure! Here's a joke:"

    mock_agent_client.ainvoke = AsyncMock(
        return_value=ChatMessage(type="ai", content=RESPONSE),
    )

    assert at.chat_message[0].avatar == "assistant"
    assert at.chat_message[0].markdown[0].value.startswith(WELCOME_START)

    at.sidebar.toggle[0].set_value(False)  # Use Streaming = False
    at.chat_input[0].set_value(PROMPT).run()
    print(at)
    assert at.chat_message[0].avatar == "user"
    assert at.chat_message[0].markdown[0].value == PROMPT
    assert at.chat_message[1].avatar == "assistant"
    assert at.chat_message[1].markdown[0].value == RESPONSE
    assert not at.exception


def test_app_settings(mock_agent_client):
    """Test the full app - happy path"""
    at = AppTest.from_file("../../src/streamlit_app.py")
    at.query_params["user_id"] = "1234"
    at.run()

    PROMPT = "Know any jokes?"
    RESPONSE = "Sure! Here's a joke:"

    mock_agent_client.ainvoke = AsyncMock(
        return_value=ChatMessage(type="ai", content=RESPONSE),
    )

    at.sidebar.toggle[0].set_value(False)  # Use Streaming = False
    assert at.sidebar.selectbox[0].value == "gpt-5-nano"
    assert mock_agent_client.agent == "rag-assistant"
    at.sidebar.selectbox[0].set_value("gpt-5-mini")
    assert len(at.sidebar.selectbox) == 1
    at.chat_input[0].set_value(PROMPT).run()
    print(at)

    # Basic checks
    assert at.chat_message[0].avatar == "user"
    assert at.chat_message[0].markdown[0].value == PROMPT
    assert at.chat_message[1].avatar == "assistant"
    assert at.chat_message[1].markdown[0].value == RESPONSE

    # Check the args match the settings
    assert mock_agent_client.agent == "rag-assistant"
    mock_agent_client.ainvoke.assert_called_with(
        message=PROMPT,
        model=OpenAIModelName.GPT_5_MINI,
        thread_id=at.session_state.thread_id,
        user_id="1234",
    )
    assert not at.exception


def test_app_thread_id_history(mock_agent_client):
    """Test the thread_id is generated"""

    at = AppTest.from_file("../../src/streamlit_app.py").run()

    # Reset and set thread_id
    at = AppTest.from_file("../../src/streamlit_app.py")
    at.query_params["thread_id"] = "1234"
    HISTORY = [
        ChatMessage(type="human", content="What is the weather?"),
        ChatMessage(type="ai", content="The weather is sunny."),
    ]
    mock_agent_client.get_history.return_value = ChatHistory(messages=HISTORY)
    at.run()
    print(at)
    assert at.session_state.thread_id == "1234"
    # No agent in the URL, so history is read through the client's selected agent.
    mock_agent_client.get_history.assert_called_with(thread_id="1234", agent="rag-assistant")
    assert at.chat_message[0].avatar == "user"
    assert at.chat_message[0].markdown[0].value == "What is the weather?"
    assert at.chat_message[1].avatar == "assistant"
    assert at.chat_message[1].markdown[0].value == "The weather is sunny."
    assert not at.exception


def test_app_resume_with_agent_param(mock_agent_client):
    """An ?agent= URL param scopes the resumed history to that agent's graph."""

    at = AppTest.from_file("../../src/streamlit_app.py")
    at.query_params["thread_id"] = "1234"
    at.query_params["agent"] = "chatbot"
    HISTORY = [
        ChatMessage(type="human", content="What is the weather?"),
        ChatMessage(type="ai", content="The weather is sunny."),
    ]
    mock_agent_client.get_history.return_value = ChatHistory(messages=HISTORY)
    at.run()
    print(at)
    assert at.session_state.thread_id == "1234"
    # History is fetched through the agent named in the URL, not the default.
    mock_agent_client.get_history.assert_called_with(thread_id="1234", agent="rag-assistant")
    assert at.chat_message[0].markdown[0].value == "What is the weather?"
    assert at.chat_message[1].markdown[0].value == "The weather is sunny."
    assert not at.exception


def test_app_feedback(mock_agent_client):
    """TODO: Can't figure out how to interact with st.feedback"""

    pass


@pytest.mark.asyncio
async def test_app_streaming(mock_agent_client):
    """Test the app with streaming enabled - including tool messages"""
    at = AppTest.from_file("../../src/streamlit_app.py").run()

    # Setup mock streaming response
    PROMPT = "What is 6 * 7?"
    ai_with_tool = ChatMessage(
        type="ai",
        content="",
        tool_calls=[{"name": "calculator", "id": "test_call_id", "args": {"expression": "6 * 7"}}],
    )
    tool_message = ChatMessage(type="tool", content="42", tool_call_id="test_call_id")
    final_ai_message = ChatMessage(type="ai", content="The answer is 42")

    messages = [ai_with_tool, tool_message, final_ai_message]

    async def amessage_iter() -> AsyncGenerator[ChatMessage, None]:
        for m in messages:
            yield m

    mock_agent_client.astream = Mock(return_value=amessage_iter())

    at.toggle[0].set_value(True)  # Use Streaming = True
    at.chat_input[0].set_value(PROMPT).run()
    print(at)

    assert at.chat_message[0].avatar == "user"
    assert at.chat_message[0].markdown[0].value == PROMPT
    response = at.chat_message[1]
    tool_status = response.status[0]
    assert response.avatar == "assistant"
    assert tool_status.label == "正在检索知识库"
    assert tool_status.icon == ":material/check:"
    assert tool_status.markdown[0].value == "检索已结束。"
    assert response.markdown[-1].value == "The answer is 42"
    assert not at.exception


@pytest.mark.asyncio
async def test_app_init_error(mock_agent_client):
    """Test the app with an error in the agent initialization"""
    at = AppTest.from_file("../../src/streamlit_app.py").run()

    # Setup mock streaming response
    PROMPT = "What is 6 * 7?"
    mock_agent_client.astream.side_effect = AgentClientError("Error connecting to agent")

    at.toggle[0].set_value(True)  # Use Streaming = True
    at.chat_input[0].set_value(PROMPT).run()
    print(at)

    assert at.chat_message[0].avatar == "assistant"
    assert at.chat_message[1].avatar == "user"
    assert at.chat_message[1].markdown[0].value == PROMPT
    assert at.error[0].value == "Error connecting to agent"
    assert not at.exception


def test_app_new_chat_btn(mock_agent_client):
    at = AppTest.from_file("../../src/streamlit_app.py").run()
    thread_id_a = at.session_state.thread_id

    at.sidebar.button[0].click().run()

    assert at.session_state.thread_id != thread_id_a
    assert not at.exception


@pytest.fixture
def mock_threads_data():
    """Fixture providing dummy thread data for caching tests."""
    return UserThreads(
        threads=[
            ThreadSummary(
                thread_id="thread-1111-2222",
                agent_id="rag-assistant",
                updated_at="2026-07-31T20:14:19.804150+00:00",
                title="What is Python?",
            )
        ]
    )


def test_app_thread_caching_sidebar(mock_agent_client, mock_threads_data):
    """Verify thread list is fetched via get_user_threads and rendered in sidebar history."""
    mock_agent_client.get_user_threads = Mock(return_value=mock_threads_data)

    at = AppTest.from_file("../../src/streamlit_app.py")
    at.query_params["user_id"] = "user-123"
    at.run()

    mock_agent_client.get_user_threads.assert_called_with(
        user_id="user-123", agent="rag-assistant", limit=20
    )

    sidebar_buttons = [b.label for b in at.sidebar.button]
    assert "What is Python?" in sidebar_buttons
    assert not at.exception


def test_app_thread_click_loads_history(mock_agent_client, mock_threads_data):
    """Verify clicking a sidebar thread loads that conversation into the chat."""
    mock_agent_client.get_user_threads = Mock(return_value=mock_threads_data)
    mock_agent_client.get_history = Mock(
        return_value=ChatHistory(
            messages=[
                ChatMessage(type="human", content="What is Python?"),
                ChatMessage(type="ai", content="A programming language."),
            ]
        )
    )

    at = AppTest.from_file("../../src/streamlit_app.py")
    at.query_params["user_id"] = "user-123"
    at.run()

    at.button(key="thread_thread-1111-2222").click().run()

    mock_agent_client.get_history.assert_called_with(
        thread_id="thread-1111-2222", agent="rag-assistant"
    )
    assert at.session_state.thread_id == "thread-1111-2222"
    assert [m.content for m in at.session_state.messages] == [
        "What is Python?",
        "A programming language.",
    ]
    assert not at.exception


def test_app_thread_click_history_error(mock_agent_client, mock_threads_data):
    """Verify a failed history fetch surfaces an error and leaves the current chat alone."""
    mock_agent_client.get_user_threads = Mock(return_value=mock_threads_data)
    mock_agent_client.get_history = Mock(side_effect=AgentClientError("service down"))

    at = AppTest.from_file("../../src/streamlit_app.py")
    at.query_params["user_id"] = "user-123"
    at.run()
    original_thread_id = at.session_state.thread_id

    at.button(key="thread_thread-1111-2222").click().run()

    assert any("Could not load that conversation." in error.value for error in at.error)
    assert at.session_state.thread_id == original_thread_id
    assert not at.exception


def test_app_thread_fetch_error_shows_caption(mock_agent_client):
    """Verify the sidebar degrades gracefully when the threads endpoint fails."""
    mock_agent_client.get_user_threads = Mock(side_effect=AgentClientError("service down"))

    at = AppTest.from_file("../../src/streamlit_app.py")
    at.query_params["user_id"] = "user-123"
    at.run()

    assert any("暂时无法加载历史会话" in caption.value for caption in at.caption)
    assert not any("service down" in caption.value for caption in at.caption)
    assert not at.exception
