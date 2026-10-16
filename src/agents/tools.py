from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from rag.runtime import get_knowledge_base
from schema.errors import AgentServiceError


def ensure_rag_available() -> None:
    get_knowledge_base()


@tool("Database_Search")
async def database_search(query: str, config: RunnableConfig) -> str:
    """Search the signed-in user's knowledge base and return evidence with source metadata."""
    owner = config.get("configurable", {}).get("user_id")
    if not owner:
        raise AgentServiceError(
            "SESSION_EXPIRED", detail="Search requires a server-verified account", status_code=401
        )
    result = await get_knowledge_base().search(owner, query)
    return result.model_dump_json()
