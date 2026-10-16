import math

import httpx

from core import settings


async def rerank(query: str, texts: list[str]) -> list[tuple[int, float]]:
    if not settings.DASHSCOPE_API_KEY:
        raise ValueError("DASHSCOPE_API_KEY missing for reranking")
    async with httpx.AsyncClient(timeout=settings.RAG_RERANK_TIMEOUT) as client:
        response = await client.post(
            settings.RAG_RERANK_URL,
            headers={"Authorization": f"Bearer {settings.DASHSCOPE_API_KEY.get_secret_value()}"},
            json={
                "model": settings.RAG_RERANK_MODEL,
                "input": {"query": query, "documents": texts},
                "parameters": {"top_n": len(texts), "return_documents": False},
            },
        )
        response.raise_for_status()
        rows = response.json()["output"]["results"]
        results = [(int(r["index"]), float(r["relevance_score"])) for r in rows]
        if (
            len(results) != len(texts)
            or {i for i, _ in results} != set(range(len(texts)))
            or not all(math.isfinite(s) for _, s in results)
        ):
            raise ValueError("Invalid rerank response")
        return sorted(results, key=lambda item: item[1], reverse=True)
