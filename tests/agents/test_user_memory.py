import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.memory import InMemoryStore

from agents.user_memory import memory_tools, read_user_memories

pytestmark = pytest.mark.asyncio


def build_memory_graph(store):
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode(memory_tools))
    graph.set_entry_point("tools")
    graph.add_edge("tools", END)
    return graph.compile(store=store, checkpointer=InMemorySaver())


async def call_tool(graph, user_id, thread_id, name, args):
    return await graph.ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"name": name, "args": args, "id": "call-1", "type": "tool_call"}],
                )
            ]
        },
        {"configurable": {"user_id": user_id, "thread_id": thread_id}},
    )


async def test_memory_crosses_threads_and_isolates_users():
    store = InMemoryStore()
    graph = build_memory_graph(store)
    await call_tool(
        graph, "alice", "chat-1", "remember_memory", {"key": "language", "text": "Prefer Chinese"}
    )
    result = await call_tool(graph, "alice", "chat-2", "recall_memories", {})
    assert "Prefer Chinese" in result["messages"][-1].content
    other = await call_tool(graph, "bob", "chat-3", "recall_memories", {})
    assert other["messages"][-1].content == "{}"


async def test_memory_can_be_updated_and_deleted():
    store = InMemoryStore()
    graph = build_memory_graph(store)
    for text in ["Prefer English", "Prefer Chinese"]:
        await call_tool(graph, "alice", text, "remember_memory", {"key": "language", "text": text})
    memories = await read_user_memories(store, "alice")
    assert "Prefer Chinese" in memories
    assert "Prefer English" not in memories
    await call_tool(graph, "alice", "delete", "forget_memory", {"key": "language"})
    assert await read_user_memories(store, "alice") == "{}"


async def test_research_model_receives_saved_memory(monkeypatch):
    from importlib import import_module
    from unittest.mock import AsyncMock

    from langgraph.runtime import Runtime

    module = import_module("agents.research_assistant")
    store = InMemoryStore()
    await call_tool(
        build_memory_graph(store),
        "alice",
        "old",
        "remember_memory",
        {"key": "language", "text": "Prefer Chinese"},
    )
    runner = AsyncMock()
    runner.ainvoke.return_value = AIMessage(content="OK")
    captured = []
    monkeypatch.setattr(module, "get_model", lambda name: object())
    monkeypatch.setattr(module, "get_runtime", lambda: Runtime(store=store))
    monkeypatch.setattr(
        module, "wrap_model", lambda model, memories: captured.append(memories) or runner
    )
    await module.acall_model(
        {"messages": [HumanMessage(content="Hello")], "remaining_steps": 10},
        {"configurable": {"user_id": "alice", "thread_id": "new"}},
    )
    assert "Prefer Chinese" in captured[0]
