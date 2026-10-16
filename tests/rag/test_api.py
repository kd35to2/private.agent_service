import httpx
import pytest
from fastapi import Request

from accounts.models import User
from service import app
from service.account_auth import current_user


@pytest.mark.asyncio
async def test_document_api_authentication_ownership_upload_and_source(knowledge, monkeypatch):
    service, _, _ = knowledge
    monkeypatch.setattr(app.state, "knowledge_base", service, raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/knowledge/documents")
        assert response.status_code == 401

        async def user(request: Request):
            return User(
                id=request.headers.get("x-test-owner", "alice"),
                username="test",
                password_hash="unused",
            )

        app.dependency_overrides[current_user] = user
        try:
            response = await client.post(
                "/knowledge/documents",
                files={"file": ("政策.txt", "休假制度：年假15天。".encode())},
            )
            assert response.status_code == 200
            doc_id = response.json()["document_id"]
            rows = (await client.get(f"/knowledge/documents/{doc_id}/chunks")).json()["chunks"]
            assert rows[0]["page"] is None
            path = f"/knowledge/documents/{doc_id}/chunks/{rows[0]['id']}"
            assert (await client.get(path)).status_code == 200
            assert (await client.get(path, headers={"x-test-owner": "bob"})).status_code == 404
            assert (
                await client.post(
                    "/knowledge/search", json={"query": "年假"}, headers={"x-test-owner": "bob"}
                )
            ).json()["results"] == []
            assert (
                await client.post("/knowledge/documents", files={"file": ("bad.exe", b"invalid")})
            ).status_code == 422
            assert (await client.delete(f"/knowledge/documents/{doc_id}")).status_code == 204
            assert (await client.get(path)).status_code == 404
        finally:
            app.dependency_overrides.pop(current_user, None)
