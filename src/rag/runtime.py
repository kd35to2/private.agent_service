from rag.documents import KnowledgeBase
from schema.errors import AgentServiceError

_service: KnowledgeBase | None = None


def configure(service: KnowledgeBase | None) -> None:
    global _service
    _service = service


def get_knowledge_base() -> KnowledgeBase:
    if _service is None:
        raise AgentServiceError(
            "KNOWLEDGE_BASE_UNAVAILABLE",
            detail="Private knowledge base requires account database initialization",
        )
    return _service
