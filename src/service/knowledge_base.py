from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse

from accounts.models import User
from core import settings
from rag.documents import KnowledgeBase, failure
from rag.schemas import SearchInput, SearchResult
from service.account_auth import current_user


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/knowledge", tags=["Knowledge base"], dependencies=[Depends(private_response)]
)
SignedIn = Annotated[User, Depends(current_user)]


def knowledge_base(request: Request) -> KnowledgeBase:
    service = getattr(request.app.state, "knowledge_base", None)
    if service is None:
        raise failure("KNOWLEDGE_BASE_UNAVAILABLE")
    return service


@router.get("", response_class=HTMLResponse)
async def knowledge_page():
    return HTMLResponse(
        Path(__file__).with_name("knowledge_page.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/documents")
async def documents(request: Request, user: SignedIn):
    return {"documents": await knowledge_base(request).list_documents(user.id)}


@router.post("/documents")
async def upload(
    request: Request,
    user: SignedIn,
    file: Annotated[UploadFile, File()],
    document_id: Annotated[str | None, Form()] = None,
):
    try:
        content = await file.read(settings.RAG_MAX_UPLOAD_MB * 1024 * 1024 + 1)
    finally:
        await file.close()
    return await knowledge_base(request).ingest(user.id, file.filename or "", content, document_id)


@router.post("/documents/{document_id}/reindex")
async def reindex(document_id: str, request: Request, user: SignedIn):
    return await knowledge_base(request).reindex(user.id, document_id)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, request: Request, user: SignedIn):
    await knowledge_base(request).delete(user.id, document_id)


@router.get("/documents/{document_id}/chunks")
async def chunks(
    document_id: str,
    request: Request,
    user: SignedIn,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    return await knowledge_base(request).chunks(user.id, document_id, offset, limit)


@router.get("/documents/{document_id}/chunks/{chunk_id}")
async def source(document_id: str, chunk_id: str, request: Request, user: SignedIn):
    return await knowledge_base(request).chunk(user.id, document_id, chunk_id)


@router.post("/search", response_model=SearchResult)
async def search(data: SearchInput, request: Request, user: SignedIn):
    return await knowledge_base(request).search(user.id, data.query, data.limit)
