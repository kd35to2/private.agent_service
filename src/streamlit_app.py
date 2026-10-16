import asyncio
import json
import logging
import os
import urllib.parse
import uuid
from collections.abc import AsyncGenerator

import streamlit as st
from dotenv import load_dotenv

from client import AgentClient, AgentClientError
from schema import ChatHistory, ChatMessage, UserThreads
from schema.errors import PUBLIC_ERROR_MESSAGES
from voice import VoiceManager

# A Streamlit app for interacting with the langgraph agent via a simple chat interface.
# The app has three main functions which are all run async:

# - main() - sets up the streamlit app and high level structure
# - draw_messages() - draws a set of chat messages - either replaying existing messages
#   or streaming new ones.
# - handle_feedback() - Draws a feedback widget and records feedback from the user.

# The app heavily uses AgentClient to interact with the agent's FastAPI endpoints.


APP_TITLE = "个人知识库"
APP_ICON = "🧰"
USER_ID_COOKIE = "user_id"
logger = logging.getLogger(__name__)


def get_or_create_user_id() -> str:
    """Get the user ID from session state or URL parameters, or create a new one if it doesn't exist."""
    # Check if user_id exists in session state
    if USER_ID_COOKIE in st.session_state:
        return st.session_state[USER_ID_COOKIE]

    # Try to get from URL parameters using the new st.query_params
    if USER_ID_COOKIE in st.query_params:
        user_id = st.query_params[USER_ID_COOKIE]
        st.session_state[USER_ID_COOKIE] = user_id
        return user_id

    # Generate a new user_id if not found
    user_id = str(uuid.uuid4())

    # Store in session state for this session
    st.session_state[USER_ID_COOKIE] = user_id

    # Also add to URL parameters so it can be bookmarked/shared
    st.query_params[USER_ID_COOKIE] = user_id

    return user_id


@st.cache_data(ttl=600, show_spinner=False)
def fetch_user_threads_cached(
    base_url: str,
    user_id: str,
    agent_id: str | None = None,
    limit: int = 20,
    _access_token: str | None = None,
) -> UserThreads:
    """
    Fetch and cache user threads using the new synchronous get_user_threads method.
    """
    client = AgentClient(base_url=base_url, get_info=False, access_token=_access_token)
    return client.get_user_threads(user_id=user_id, agent=agent_id, limit=limit)


async def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        menu_items={},
    )

    # Hide the streamlit upper-right chrome
    st.html(
        """
        <style>
        [data-testid="stStatusWidget"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
            }
        </style>
        """,
    )
    if st.get_option("client.toolbarMode") != "minimal":
        st.set_option("client.toolbarMode", "minimal")
        await asyncio.sleep(0.1)
        st.rerun()

    load_dotenv()
    account_mode = os.getenv("USER_AUTH_ENABLED", "false").lower() == "true"
    agent_url = (
        os.getenv("AGENT_URL")
        or f"http://{os.getenv('HOST', '127.0.0.1')}:{os.getenv('PORT', '8080')}"
    )
    account_url = os.getenv("PUBLIC_AGENT_URL", agent_url).rstrip("/") + "/account"
    if account_mode:
        token = st.context.cookies.get("agent_session")
        if not token:
            st.title("登录后开始聊天")
            st.link_button("登录 / 注册", account_url)
            st.caption("账号页面登录后，点击“进入聊天”。")
            st.stop()
        auth_client = AgentClient(base_url=agent_url, get_info=False, access_token=token)
        try:
            account = auth_client.get_current_user()
        except AgentClientError:
            st.warning("登录已过期或已退出，请重新登录。")
            st.link_button("登录 / 注册", account_url)
            st.stop()
        user_id = account["id"]
        if st.session_state.get("account_id") != user_id:
            st.session_state.clear()
            st.session_state.account_id = user_id
        st.query_params.pop("user_id", None)
        st.sidebar.caption(f"已登录：{account['username']}")
        st.sidebar.link_button("账号管理 / 修改密码 / 退出", account_url)
        st.sidebar.link_button("知识库管理 / 上传文档", agent_url.rstrip("/") + "/knowledge")
    else:
        token = None
        user_id = get_or_create_user_id()

    if "agent_client" not in st.session_state:
        load_dotenv()
        agent_url = os.getenv("AGENT_URL")
        if not agent_url:
            host = os.getenv("HOST", "0.0.0.0")
            port = os.getenv("PORT", 8080)
            agent_url = f"http://{host}:{port}"
        try:
            with st.spinner("Connecting to agent service..."):
                if account_mode:
                    st.session_state.agent_client = AgentClient(
                        base_url=agent_url, access_token=token
                    )
                else:
                    st.session_state.agent_client = AgentClient(base_url=agent_url)
        except AgentClientError as e:
            logger.warning("Agent service connection failed: %s", e)
            st.error("暂时无法连接服务，请稍后重试。")
            st.markdown("The service might be booting up. Try again in a few seconds.")
            st.stop()
    agent_client: AgentClient = st.session_state.agent_client
    if account_mode:
        agent_client.access_token = token

    # Initialize voice manager (once per session)
    if "voice_manager" not in st.session_state:
        st.session_state.voice_manager = VoiceManager.from_env()
    voice = st.session_state.voice_manager

    if "thread_id" not in st.session_state:
        thread_id = st.query_params.get("thread_id")
        if not thread_id:
            thread_id = str(uuid.uuid4())
            messages = []
        else:
            # Read the agent from the URL so history is fetched through the graph that
            # created the thread.
            resume_agent = "rag-assistant"
            try:
                messages: ChatHistory = agent_client.get_history(
                    thread_id=thread_id, agent=resume_agent
                ).messages
            except AgentClientError:
                st.error("No message history found for this Thread ID.")
                messages = []
        st.session_state.messages = messages
        st.session_state.thread_id = thread_id

    # Keep thread_id in the URL so the address bar is directly shareable.
    st.query_params["thread_id"] = st.session_state.thread_id

    # Config options
    with st.sidebar:
        st.header(f"{APP_ICON} {APP_TITLE}")

        ""
        "上传自己的资料，检索原文，并获得带来源引用的回答。"
        ""

        if st.button(":material/chat: New Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.thread_id = str(uuid.uuid4())
            # Clear saved audio when starting new chat
            if "last_audio" in st.session_state:
                del st.session_state.last_audio
            st.rerun()

        with st.expander(":material/history: Previous Chats", expanded=False):
            try:
                url_agent = st.query_params.get("agent")
                if url_agent in [a.key for a in agent_client.info.agents]:
                    agent_client.agent = url_agent
                else:
                    agent_client.agent = agent_client.info.default_agent
                user_threads = fetch_user_threads_cached(
                    base_url=agent_client.base_url,
                    user_id=user_id,
                    agent_id=agent_client.agent,
                    limit=20,
                    _access_token=token,
                )
                thread_list = user_threads.threads
            except Exception:
                logger.exception("Conversation list loading failed")
                st.caption("暂时无法加载历史会话，请稍后重试。")
                thread_list = []

            for t in thread_list:
                label = t.title or f"Chat {t.thread_id[:8]}"
                if st.button(label, key=f"thread_{t.thread_id}", use_container_width=True):
                    try:
                        history: ChatHistory = agent_client.get_history(
                            thread_id=t.thread_id, agent=t.agent_id
                        )
                    except AgentClientError:
                        st.error("Could not load that conversation.")
                        continue
                    st.session_state.messages = history.messages
                    st.session_state.thread_id = t.thread_id
                    st.query_params["thread_id"] = t.thread_id
                    if "last_audio" in st.session_state:
                        del st.session_state.last_audio
                    st.rerun()

        with st.popover(":material/settings: Settings", use_container_width=True):
            model_idx = agent_client.info.models.index(agent_client.info.default_model)
            model = st.selectbox("LLM to use", options=agent_client.info.models, index=model_idx)
            agent_client.agent = "rag-assistant"
            st.query_params.pop("agent", None)
            use_streaming = st.toggle("Stream results", value=True)
            # Audio toggle with callback: clears cached audio when toggled off
            enable_audio = st.toggle(
                "Enable audio generation",
                value=True,
                disabled=not voice or not voice.tts,
                help="Configure VOICE_TTS_PROVIDER in .env to enable"
                if not voice or not voice.tts
                else None,
                on_change=lambda: (
                    st.session_state.pop("last_audio", None)
                    if not st.session_state.get("enable_audio", True)
                    else None
                ),
                key="enable_audio",
            )

            # Display user ID (for debugging or user information)
            st.text_input("User ID (read-only)", value=user_id, disabled=True)

        with st.expander("数据与隐私"):
            st.write(
                "文档按登录账号隔离。嵌入、重排和回答会调用已配置的模型服务。仅在显式启用时记录外部追踪。"
            )

        @st.dialog("Share/resume chat")
        def share_chat_dialog() -> None:
            # st.context.url is the browser URL (with query string stripped). Rebuild
            # the params, including the agent so the thread resumes through the right graph.
            if not st.context.url:
                st.error("Could not determine the app URL to build a shareable link.")
                return
            query = urllib.parse.urlencode(
                {
                    "thread_id": st.session_state.thread_id,
                    "agent": agent_client.agent,
                    **({} if account_mode else {USER_ID_COOKIE: user_id}),
                }
            )
            chat_url = f"{st.context.url}?{query}"
            st.markdown(f"**Chat URL:**\n```text\n{chat_url}\n```")
            st.info(
                "登录原账号后可恢复此会话。"
                if account_mode
                else "Copy the above URL to share or revisit this chat"
            )

        if st.button(":material/upload: Share/resume chat", use_container_width=True):
            share_chat_dialog()

    # Draw existing messages
    messages: list[ChatMessage] = st.session_state.messages

    if len(messages) == 0:
        with st.chat_message("ai"):
            st.write(
                "你好，我是你的知识库助手。请先在左侧“知识库管理”中上传资料；我会检索你的文档，并为回答提供原文引用。"
            )

    # draw_messages() expects an async iterator over messages
    async def amessage_iter() -> AsyncGenerator[ChatMessage, None]:
        for m in messages:
            yield m

    await draw_messages(amessage_iter())

    # Render saved audio for the last AI message (if it exists)
    # This ensures audio persists across st.rerun() calls
    if (
        voice
        and enable_audio
        and "last_audio" in st.session_state
        and st.session_state.last_message
        and len(messages) > 0
        and messages[-1].type == "ai"
    ):
        with st.session_state.last_message:
            audio_data = st.session_state.last_audio
            st.audio(audio_data["data"], format=audio_data["format"])

    # Generate new message if the user provided new input
    # Use voice manager if available, otherwise fall back to regular input
    # REQUIRED: Set VOICE_STT_PROVIDER, VOICE_TTS_PROVIDER, OPENAI_API_KEY
    # in app .env (NOT service .env) to enable voice features.
    if voice:
        user_input = voice.get_chat_input()
    else:
        user_input = st.chat_input()

    if user_input:
        is_first_message = len(messages) == 0
        messages.append(ChatMessage(type="human", content=user_input))
        st.chat_message("human").write(user_input)
        try:
            if use_streaming:
                stream = agent_client.astream(
                    message=user_input,
                    model=model,
                    thread_id=st.session_state.thread_id,
                    user_id=user_id,
                )
                await draw_messages(stream, is_new=True)
                # Generate TTS audio for streaming response
                # Note: draw_messages() stores the final message in st.session_state.messages
                # and the container reference in st.session_state.last_message
                if voice and enable_audio and st.session_state.messages:
                    last_msg = st.session_state.messages[-1]
                    # Only generate audio for AI responses with content
                    if last_msg.type == "ai" and last_msg.content:
                        # Use audio_only=True since text was already streamed by draw_messages()
                        voice.render_message(
                            last_msg.content,
                            container=st.session_state.last_message,
                            audio_only=True,
                        )
            else:
                response = await agent_client.ainvoke(
                    message=user_input,
                    model=model,
                    thread_id=st.session_state.thread_id,
                    user_id=user_id,
                )
                messages.append(response)
                # Render AI response with optional voice
                with st.chat_message("ai"):
                    if voice and enable_audio:
                        voice.render_message(response.content)
                    else:
                        st.write(response.content)
            if is_first_message:
                fetch_user_threads_cached.clear()
            st.rerun()  # Clear stale containers
        except AgentClientError as e:
            st.error(str(e))
            st.stop()

    # If messages have been generated, show feedback widget
    if len(messages) > 0 and st.session_state.last_message:
        with st.session_state.last_message:
            await handle_feedback()


async def draw_messages(
    messages_agen: AsyncGenerator[ChatMessage | str, None],
    is_new: bool = False,
) -> None:
    """
    Draws a set of chat messages - either replaying existing messages
    or streaming new ones.

    This function has additional logic to handle streaming tokens and tool calls.
    - Use a placeholder container to render streaming tokens as they arrive.
    - Use a status container to render tool calls. Track the tool inputs and outputs
      and update the status container accordingly.

    The function also needs to track the last message container in session state
    since later messages can draw to the same container. This is also used for
    drawing the feedback widget in the latest chat message.

    Args:
        messages_aiter: An async iterator over messages to draw.
        is_new: Whether the messages are new or not.
    """

    # Keep track of the last message container
    last_message_type = None
    st.session_state.last_message = None

    # Placeholder for intermediate streaming tokens
    streaming_content = ""
    streaming_placeholder = None
    pending_tools = {}

    async def next_message():
        try:
            return await anext(messages_agen, None)
        except Exception:
            for tool_status in pending_tools.values():
                tool_status.update(state="error", expanded=True)
            raise

    # Iterate over the messages and draw them
    while msg := await next_message():
        # str message represents an intermediate token being streamed
        if isinstance(msg, str):
            # If placeholder is empty, this is the first token of a new message
            # being streamed. We need to do setup.
            if not streaming_placeholder:
                if last_message_type != "ai":
                    last_message_type = "ai"
                    st.session_state.last_message = st.chat_message("ai")
                with st.session_state.last_message:
                    streaming_placeholder = st.empty()

            streaming_content += msg
            streaming_placeholder.write(streaming_content)
            continue
        if not isinstance(msg, ChatMessage):
            raise AgentClientError(PUBLIC_ERROR_MESSAGES["INVALID_RESPONSE"])

        match msg.type:
            # A message from the user, the easiest case
            case "human":
                last_message_type = "human"
                st.chat_message("human").write(msg.content)

            # A message from the agent is the most complex case, since we need to
            # handle streaming tokens and tool calls.
            case "ai":
                # If we're rendering new messages, store the message in session state
                if is_new:
                    st.session_state.messages.append(msg)

                # If the last message type was not AI, create a new chat message
                if last_message_type != "ai":
                    last_message_type = "ai"
                    st.session_state.last_message = st.chat_message("ai")

                with st.session_state.last_message:
                    # If the message has content, write it out.
                    # Reset the streaming variables to prepare for the next message.
                    if msg.content:
                        if streaming_placeholder:
                            streaming_placeholder.write(msg.content)
                            streaming_content = ""
                            streaming_placeholder = None
                        else:
                            st.write(msg.content)

                    if msg.custom_data:
                        for notice in msg.custom_data.get("notices", []):
                            st.caption(notice)
                        for citation in msg.custom_data.get("citations", []):
                            location = (
                                f"第 {citation['page']} 页"
                                if citation.get("page")
                                else f"片段 {citation['chunk_index']}"
                            )
                            label = f"[{citation['citation']}] {citation['document_name']} · v{citation['version']} · {location}"
                            with st.expander(label):
                                st.text(citation["text"])
                                if citation["start_index"] >= 0:
                                    st.caption(f"原文字符起始位置：{citation['start_index']}")

                    if msg.tool_calls:
                        # Create a status container for each tool call and store the
                        # status container by ID to ensure results are mapped to the
                        # correct status container.
                        for tool_call in msg.tool_calls:
                            status = st.status(
                                "正在检索知识库", state="running" if is_new else "complete"
                            )
                            pending_tools[tool_call["id"]] = status

            case "tool":
                if is_new:
                    st.session_state.messages.append(msg)
                tool_status = pending_tools.pop(msg.tool_call_id, None)
                if tool_status is not None:
                    try:
                        result = json.loads(msg.content)
                        tool_status.write(f"检索到 {len(result.get('results', []))} 个相关片段。")
                    except (ValueError, AttributeError):
                        tool_status.write("检索已结束。")
                    tool_status.update(state="complete")

            case "custom":
                raise AgentClientError(PUBLIC_ERROR_MESSAGES["INVALID_RESPONSE"])

            case _:
                raise AgentClientError(PUBLIC_ERROR_MESSAGES["INVALID_RESPONSE"])

    if pending_tools:
        for tool_status in pending_tools.values():
            tool_status.update(state="error", expanded=True)
        st.warning(
            "工具执行中断，没有返回完整结果。请查看错误提示，检查知识库或工具配置后新建会话重试。"
            if is_new
            else "这段历史中有未完成的工具调用，未保存对应结果。修复配置后请新建会话重试。"
        )


async def handle_feedback() -> None:
    """Draws a feedback widget and records feedback from the user."""

    # Keep track of last feedback sent to avoid sending duplicates
    if "last_feedback" not in st.session_state:
        st.session_state.last_feedback = (None, None)

    latest_run_id = st.session_state.messages[-1].run_id
    feedback = st.feedback("stars", key=latest_run_id)

    # If the feedback value or run ID has changed, send a new feedback record
    if feedback is not None and (latest_run_id, feedback) != st.session_state.last_feedback:
        # Normalize the feedback value (an index) to a score between 0 and 1
        normalized_score = (feedback + 1) / 5.0

        agent_client: AgentClient = st.session_state.agent_client
        try:
            await agent_client.acreate_feedback(
                run_id=latest_run_id,
                key="human-feedback-stars",
                score=normalized_score,
                kwargs={"comment": "In-line human feedback"},
            )
        except AgentClientError:
            st.error("反馈未能提交，请稍后重试。")
            st.stop()
        st.session_state.last_feedback = (latest_run_id, feedback)
        st.toast("Feedback recorded", icon=":material/reviews:")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AgentClientError as error:
        st.error(str(error))
    except Exception:
        logger.exception("Unexpected chat interface error")
        st.error(PUBLIC_ERROR_MESSAGES["AGENT_EXECUTION_FAILED"])
