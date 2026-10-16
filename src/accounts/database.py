from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from accounts.models import Base
from core import settings
from core.settings import DatabaseType


class AccountDatabase:
    def __init__(self, url: str | URL):
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def setup(self) -> None:
        import rag.models  # noqa: F401 - register knowledge-base tables

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()


def create_account_database() -> AccountDatabase:
    if settings.DATABASE_TYPE != DatabaseType.POSTGRES:
        raise ValueError("USER_AUTH_ENABLED requires PostgreSQL")
    return AccountDatabase(
        URL.create(
            "postgresql+psycopg",
            username=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD.get_secret_value()
            if settings.POSTGRES_PASSWORD
            else None,
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
        )
    )
