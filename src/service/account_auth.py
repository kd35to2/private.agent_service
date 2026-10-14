"""Cookie/bearer sessions and ownership checks for account-enabled services."""

import hashlib
import secrets
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from accounts.database import AccountDatabase
from accounts.models import AgentRun, ConversationThread, LoginSession, User
from core import settings
from schema.accounts import ChangePasswordInput, Credentials, LoginResponse, UserResponse

COOKIE_NAME = "agent_session"
bearer = HTTPBearer(auto_error=False)
password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash(secrets.token_urlsafe(32))
router = APIRouter(prefix="/auth", tags=["Accounts"])


def account_database(request: Request) -> AccountDatabase:
    if not settings.USER_AUTH_ENABLED:
        raise HTTPException(status_code=503, detail="Account authentication is not enabled")
    db = getattr(request.app.state, "account_database", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Account authentication is not enabled")
    return db


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(status_code=403, detail="Cross-origin account requests are not allowed")


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def request_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials:
        return credentials.credentials
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
    return request.cookies.get(COOKIE_NAME, "")


async def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    token = request_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=401, detail="Please sign in", headers={"WWW-Authenticate": "Bearer"}
        )
    db = account_database(request)
    async with db.sessions() as session:
        user = await session.scalar(
            select(User)
            .join(LoginSession, LoginSession.user_id == User.id)
            .where(
                LoginSession.token_hash == token_digest(token),
                LoginSession.expires_at > int(time.time()),
            )
        )
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Session expired or revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.AUTH_SESSION_DAYS * 86400,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(data: Credentials, request: Request) -> User:
    check_origin(request)
    db = account_database(request)
    hashed = await run_in_threadpool(password_hash.hash, data.password.get_secret_value())
    user = User(username=data.username, password_hash=hashed)
    async with db.sessions() as session:
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=409, detail="Username already exists")
    return user


@router.post("/login", response_model=LoginResponse)
async def login(data: Credentials, request: Request, response: Response) -> LoginResponse:
    check_origin(request)
    db = account_database(request)
    async with db.sessions() as session:
        user = await session.scalar(
            select(User).where(User.username == data.username).with_for_update()
        )
        if user is None:
            await run_in_threadpool(
                password_hash.verify, data.password.get_secret_value(), dummy_password_hash
            )
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if user.locked_until > int(time.time()):
            raise HTTPException(
                status_code=429, detail="Too many login attempts; try again in five minutes"
            )
        valid = await run_in_threadpool(
            password_hash.verify, data.password.get_secret_value(), user.password_hash
        )
        if not valid:
            user.failed_logins += 1
            if user.failed_logins >= 5:
                user.locked_until = int(time.time()) + 300
                user.failed_logins = 0
            await session.commit()
            raise HTTPException(status_code=401, detail="Invalid username or password")
        user.failed_logins = 0
        user.locked_until = 0
        token = secrets.token_urlsafe(32)
        session.add(
            LoginSession(
                token_hash=token_digest(token),
                user_id=user.id,
                expires_at=int(time.time()) + settings.AUTH_SESSION_DAYS * 86400,
            )
        )
        await session.commit()
    set_session_cookie(response, token)
    return LoginResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(current_user)], response: Response) -> User:
    response.headers["Cache-Control"] = "no-store"
    return user


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    user: Annotated[User, Depends(current_user)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    db = account_database(request)
    token = request_token(request, credentials)
    async with db.sessions() as session:
        await session.execute(
            delete(LoginSession).where(LoginSession.token_hash == token_digest(token))
        )
        await session.commit()
    response.delete_cookie(
        COOKIE_NAME, path="/", secure=settings.AUTH_COOKIE_SECURE, httponly=True, samesite="lax"
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/change-password", status_code=204)
async def change_password(
    data: ChangePasswordInput,
    request: Request,
    response: Response,
    user: Annotated[User, Depends(current_user)],
) -> None:
    db = account_database(request)
    new_hash = await run_in_threadpool(password_hash.hash, data.new_password.get_secret_value())
    async with db.sessions() as session:
        locked_user = await session.scalar(select(User).where(User.id == user.id).with_for_update())
        if locked_user is None or not await run_in_threadpool(
            password_hash.verify,
            data.current_password.get_secret_value(),
            locked_user.password_hash,
        ):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        locked_user.password_hash = new_hash
        locked_user.failed_logins = 0
        locked_user.locked_until = 0
        await session.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        await session.commit()
    response.delete_cookie(
        COOKIE_NAME, path="/", secure=settings.AUTH_COOKIE_SECURE, httponly=True, samesite="lax"
    )
    response.headers["Cache-Control"] = "no-store"


async def authorize_thread(
    request: Request,
    graph,
    agent_id: str,
    thread_id: str,
    *,
    create: bool = False,
) -> None:
    user = getattr(request.state, "user", None)
    if user is None:
        return
    if not thread_id or len(thread_id) > 128:
        raise HTTPException(status_code=422, detail="Invalid thread_id")
    db = account_database(request)
    async with db.sessions() as session:
        owner = await session.get(ConversationThread, thread_id)
        if owner:
            if owner.user_id != user.id or owner.agent_id != agent_id:
                raise HTTPException(status_code=404, detail="Conversation not found")
            return
        if not create:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # Existing anonymous checkpoints cannot be claimed by guessing a thread ID.
        checkpointer = getattr(graph, "checkpointer", None)
        if checkpointer and await checkpointer.aget_tuple(
            {"configurable": {"thread_id": thread_id}}
        ):
            raise HTTPException(status_code=404, detail="Conversation not found")
        session.add(ConversationThread(thread_id=thread_id, user_id=user.id, agent_id=agent_id))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            owner = await session.get(ConversationThread, thread_id)
            if owner is None or owner.user_id != user.id or owner.agent_id != agent_id:
                raise HTTPException(status_code=404, detail="Conversation not found")


def bind_user_input(user_input, request: Request) -> None:
    user = getattr(request.state, "user", None)
    if user is None:
        return
    if user_input.user_id is not None and user_input.user_id != user.id:
        raise HTTPException(status_code=403, detail="user_id does not match the signed-in account")
    user_input.user_id = user.id
    user_input.thread_id = user_input.thread_id or str(uuid4())


async def record_run(request: Request, run_id: str) -> None:
    user = getattr(request.state, "user", None)
    if user is not None:
        async with account_database(request).sessions() as session:
            session.add(AgentRun(run_id=run_id, user_id=user.id))
            await session.commit()


async def authorize_feedback(request: Request, run_id: str) -> None:
    user = getattr(request.state, "user", None)
    if user is not None:
        async with account_database(request).sessions() as session:
            run = await session.get(AgentRun, run_id)
            if run is None or run.user_id != user.id:
                raise HTTPException(status_code=404, detail="Run not found")
