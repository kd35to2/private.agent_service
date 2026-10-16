"""One embedding configuration shared by indexing and retrieval."""

from langchain_openai import OpenAIEmbeddings

from core.settings import settings


def embedding_configuration_error() -> str | None:
    if settings.RAG_EMBEDDING_PROVIDER == "dashscope":
        if not settings.DASHSCOPE_API_KEY:
            return "缺少千问嵌入模型的 DASHSCOPE_API_KEY"
    elif not settings.OPENAI_API_KEY:
        return "缺少用于 OpenAIEmbeddings 的 OPENAI_API_KEY"
    return None


def create_embeddings() -> OpenAIEmbeddings:
    if error := embedding_configuration_error():
        raise ValueError(error)
    if settings.RAG_EMBEDDING_PROVIDER == "dashscope":
        return OpenAIEmbeddings(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.RAG_EMBEDDING_BASE_URL
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            model=settings.RAG_EMBEDDING_MODEL or "text-embedding-v4",
            # Compatible APIs need raw text, not OpenAI tokenizer token IDs.
            check_embedding_ctx_length=False,
            chunk_size=10,
            model_kwargs={"encoding_format": "float"},
        )
    return OpenAIEmbeddings(
        api_key=settings.OPENAI_API_KEY,
        model=settings.RAG_EMBEDDING_MODEL or "text-embedding-3-small",
        base_url=settings.RAG_EMBEDDING_BASE_URL or "https://api.openai.com/v1",
    )
