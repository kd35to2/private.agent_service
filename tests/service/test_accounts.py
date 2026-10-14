import time
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, MessagesState, StateGraph
from sqlalchemy import select

from accounts.database import AccountDatabase
from accounts.models import LoginSession, User
from core import settings
from service import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def account_client(monkeypatch):
    monkeypatch.setattr(settings, "USER_AUTH_ENABLED", True)
    db = AccountDatabase("sqlite+aiosqlite:///:memory:")
    await db.setup()
    previous = getattr(app.state, "account_database", None)
    app.state.account_database = db

    async def answer(state):
        return {"messages": [AIMessage(content="OK")]}

    graph = StateGraph(MessagesState)
    graph.add_node("answer", answer)
    graph.set_entry_point("answer")
    graph.add_edge("answer", END)
    compiled = graph.compile(checkpointer=InMemorySaver())
    with (
        patch("service.service.get_agent", return_value=compiled),
        patch("service.agui.get_agent", return_value=compiled),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, db, compiled
    app.state.account_database = previous
    await db.close()


async def signup(client, username):
    response = await client.post(
        "/auth/register", json={"username": username, "password": "test-password-123"}
    )
    assert response.status_code == 201
    response = await client.post(
        "/auth/login", json={"username": username, "password": "test-password-123"}
    )
    assert response.status_code == 200
    body = response.json()
    return body["user"], {"Authorization": "Bearer " + body["access_token"]}


async def test_registration_login_and_cookie_restore(account_client):
    client, db, _ = account_client
    user, headers = await signup(client, "alice")
    assert "password_hash" not in user
    async with db.sessions() as session:
        saved = await session.get(User, user["id"])
        assert saved.password_hash.startswith("$argon2id$")
        tokens = (await session.scalars(select(LoginSession))).all()
        assert len(tokens[0].token_hash) == 64
        assert tokens[0].token_hash != headers["Authorization"].split()[1]
    assert (await client.get("/auth/me")).json()["id"] == user["id"]
    client.cookies.clear()
    assert (await client.get("/auth/me", headers=headers)).json()["id"] == user["id"]
    duplicate = await client.post(
        "/auth/register", json={"username": "alice", "password": "other-password"}
    )
    assert duplicate.status_code == 409
    wrong = await client.post(
        "/auth/login", json={"username": "alice", "password": "wrong-password"}
    )
    assert wrong.status_code == 401
    weak = await client.post("/auth/register", json={"username": "weak", "password": "123"})
    assert weak.status_code == 422


async def test_password_change_revokes_all_sessions(account_client):
    client, _, _ = account_client
    _, first = await signup(client, "alice")
    second = (
        await client.post(
            "/auth/login", json={"username": "alice", "password": "test-password-123"}
        )
    ).json()["access_token"]
    wrong = await client.post(
        "/auth/change-password",
        headers=first,
        json={"current_password": "wrong-password", "new_password": "new-password-456"},
    )
    assert wrong.status_code == 400
    changed = await client.post(
        "/auth/change-password",
        headers=first,
        json={"current_password": "test-password-123", "new_password": "new-password-456"},
    )
    assert changed.status_code == 204
    for headers in [first, {"Authorization": "Bearer " + second}]:
        assert (await client.get("/auth/me", headers=headers)).status_code == 401
    old = await client.post(
        "/auth/login", json={"username": "alice", "password": "test-password-123"}
    )
    assert old.status_code == 401
    new = await client.post(
        "/auth/login", json={"username": "alice", "password": "new-password-456"}
    )
    assert new.status_code == 200


async def test_logout_expiration_and_cross_origin(account_client):
    client, db, _ = account_client
    _, headers = await signup(client, "alice")
    assert (
        await client.post("/auth/logout", headers={"Origin": "https://evil.example"})
    ).status_code == 403
    assert (await client.post("/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/auth/me", headers=headers)).status_code == 401
    _, headers = await signup(client, "bob")
    async with db.sessions() as session:
        token = await session.scalar(select(LoginSession))
        token.expires_at = int(time.time()) - 1
        await session.commit()
    assert (await client.get("/auth/me", headers=headers)).status_code == 401


async def test_accounts_own_threads_and_identity(account_client):
    client, _, graph = account_client
    alice, alice_headers = await signup(client, "alice")
    bob, bob_headers = await signup(client, "bob")
    payload = {"message": "hello", "thread_id": "alice-thread"}
    assert (
        await client.post("/chatbot/invoke", json=payload, headers=alice_headers)
    ).status_code == 200
    checkpoint = await graph.checkpointer.aget_tuple(
        {"configurable": {"thread_id": "alice-thread"}}
    )
    assert checkpoint.metadata["user_id"] == alice["id"]
    assert (
        await client.post(
            "/chatbot/history", json={"thread_id": "alice-thread"}, headers=alice_headers
        )
    ).status_code == 200
    for path in ["/chatbot/invoke", "/chatbot/stream"]:
        assert (await client.post(path, json=payload, headers=bob_headers)).status_code == 404
    assert (
        await client.post(
            "/chatbot/history", json={"thread_id": "alice-thread"}, headers=bob_headers
        )
    ).status_code == 404
    spoof = await client.post(
        "/chatbot/invoke", json={"message": "hello", "user_id": alice["id"]}, headers=bob_headers
    )
    assert spoof.status_code == 403
    assert (await client.get("/chatbot/threads", headers=alice_headers)).status_code == 200
    assert (
        await client.get("/chatbot/threads", params={"user_id": alice["id"]}, headers=bob_headers)
    ).status_code == 403
    assert alice["id"] != bob["id"]


async def test_anonymous_and_agui_cannot_bypass_auth(account_client):
    client, _, _ = account_client
    client.cookies.clear()
    for path in ["/invoke", "/stream", "/history"]:
        response = await client.post(path, json={"message": "hello", "thread_id": "t"})
        assert response.status_code == 401
    assert (await client.get("/threads")).status_code == 401
    _, headers = await signup(client, "alice")
    bad = await client.post(
        "/agui/chatbot/run",
        headers=headers,
        json={
            "threadId": "agui-thread",
            "runId": "run-1",
            "state": {},
            "messages": [],
            "tools": [],
            "context": [],
            "forwardedProps": {"configurable": {"user_id": "someone-else"}},
        },
    )
    assert bad.status_code == 403


async def test_username_normalization_and_login_lock(account_client):
    client, _, _ = account_client
    created = await client.post(
        "/auth/register", json={"username": " Alice ", "password": "test-password-123"}
    )
    assert created.status_code == 201
    assert created.json()["username"] == "alice"
    for _ in range(5):
        response = await client.post(
            "/auth/login", json={"username": "alice", "password": "wrong-password"}
        )
        assert response.status_code == 401
    locked = await client.post(
        "/auth/login", json={"username": "alice", "password": "test-password-123"}
    )
    assert locked.status_code == 429


async def test_legacy_threads_and_feedback_are_not_claimable(account_client):
    client, _, graph = account_client
    await graph.ainvoke(
        {"messages": []}, {"configurable": {"thread_id": "legacy-thread", "user_id": "anonymous"}}
    )
    _, headers = await signup(client, "alice")
    legacy = await client.post(
        "/chatbot/invoke", headers=headers, json={"message": "hello", "thread_id": "legacy-thread"}
    )
    assert legacy.status_code == 404
    result = await client.post(
        "/chatbot/invoke", headers=headers, json={"message": "hello", "thread_id": "owned-thread"}
    )
    _, other_headers = await signup(client, "bob")
    forbidden = await client.post(
        "/feedback",
        headers=other_headers,
        json={"run_id": result.json()["run_id"], "key": "rating", "score": 1.0},
    )
    assert forbidden.status_code == 404
