from pydantic import BaseModel, Field


class Evidence(BaseModel):
    citation: int = 0
    document_id: str
    document_name: str
    version: int
    version_id: str
    chunk_id: str
    chunk_index: int
    page: int | None = None
    start_index: int
    text: str
    fusion_score: float = 0
    rerank_score: float | None = None
    source_url: str = ""


class SearchResult(BaseModel):
    query: str
    results: list[Evidence] = Field(default_factory=list)
    degraded: bool = False
    notices: list[str] = Field(default_factory=list)


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int | None = Field(default=None, ge=1, le=20)
