"""User-scoped memory tools shared across research-assistant conversations."""

import json

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.store.base import BaseStore


def memory_namespace(user_id: str) -> tuple[str, ...]:
    if not user_id:
        raise ValueError("A stable user_id is required for long-term memory")
    return ("users", user_id, "research-assistant", "memories")


async def read_user_memories(store: BaseStore, user_id: str) -> str:
    items = await store.asearch(memory_namespace(user_id), limit=50)
    return json.dumps({item.key: item.value["text"] for item in items}, ensure_ascii=False)


def _memory_context(runtime: ToolRuntime) -> tuple[BaseStore, tuple[str, ...]]:
    if runtime.store is None:
        raise ValueError("Long-term memory store is not configured")
    user_id = runtime.config.get("configurable", {}).get("user_id", "")
    return runtime.store, memory_namespace(user_id)


@tool
async def remember_memory(key: str, text: str, runtime: ToolRuntime) -> str:
    """Save a fact or preference the user explicitly asks you to remember across chats.

    Use a short stable key such as preferred_language. Reusing a key replaces its value.
    Only store user-provided information, never guesses, passwords, or API keys.
    """
    if not key.strip() or len(key) > 100 or not text.strip() or len(text) > 2000:
        raise ValueError("Memory needs a key of 1-100 characters and text of 1-2000 characters")
    store, namespace = _memory_context(runtime)
    await store.aput(namespace, key, {"text": text})
    return f"Saved memory: {key}"


@tool
async def recall_memories(runtime: ToolRuntime) -> str:
    """Read the current user's saved facts and preferences from previous chats."""
    store, namespace = _memory_context(runtime)
    return await read_user_memories(store, namespace[1])


@tool
async def forget_memory(key: str, runtime: ToolRuntime) -> str:
    """Delete a saved memory by its exact key when the user asks you to forget it."""
    store, namespace = _memory_context(runtime)
    await store.adelete(namespace, key)
    return f"Deleted memory: {key}"


memory_tools = [remember_memory, recall_memories, forget_memory]
