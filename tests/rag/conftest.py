import pytest_asyncio

from accounts.database import AccountDatabase
from accounts.models import User
from rag.documents import KnowledgeBase


class Embeddings:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def embed_documents(self, texts):
        self.calls += 1
        if self.fail:
            raise RuntimeError("PRIVATE_EMBEDDING_ERROR")
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, query):
        if self.fail:
            raise RuntimeError("PRIVATE_QUERY_ERROR")
        return [1.0, 0.0]


class Index:
    def __init__(self):
        self.records = {}
        self.fail_cleanup = False

    def upsert(self, owner, doc, version, chunks, vectors):
        self.records.update({c.id: (owner, version) for c in chunks})

    def search(self, owner, versions, vector, k):
        return [key for key, (o, v) in self.records.items() if o == owner and v in versions][:k]

    def delete_version(self, owner, version):
        if self.fail_cleanup:
            raise RuntimeError("cleanup interrupted")
        self.records = {
            key: (o, v) for key, (o, v) in self.records.items() if (o, v) != (owner, version)
        }


@pytest_asyncio.fixture
async def knowledge(tmp_path):
    database = AccountDatabase(f"sqlite+aiosqlite:///{tmp_path / 'knowledge.db'}")
    await database.setup()
    async with database.sessions() as session:
        session.add_all(
            [
                User(id="alice", username="alice", password_hash="unused"),
                User(id="bob", username="bob", password_hash="unused"),
            ]
        )
        await session.commit()
    embeddings, index = Embeddings(), Index()

    async def reranker(query, texts):
        return [(i, 0.9 - i * 0.01) for i in range(len(texts))]

    service = KnowledgeBase(
        database, index=index, embedding_factory=lambda: embeddings, reranker=reranker
    )
    yield service, embeddings, index
    await database.close()
