from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from rag.stores import ChromaIndex


def test_real_chroma_initialization_and_private_version_filter(tmp_path):
    index = ChromaIndex(str(tmp_path / "index"))
    with ThreadPoolExecutor(max_workers=8) as executor:
        collections = list(executor.map(lambda _: index.collection(), range(8)))
    assert all(c is collections[0] for c in collections)
    for owner, version, key in [
        ("alice", "a-old", "old"),
        ("alice", "a-new", "new"),
        ("bob", "b-new", "private"),
    ]:
        index.upsert(
            owner, "doc-" + owner, version, [SimpleNamespace(id=key, text=key)], [[1.0, 0.0]]
        )
    assert index.search("alice", ["a-new"], [1.0, 0.0], 5) == ["new"]
    assert index.search("alice", ["b-new"], [1.0, 0.0], 5) == []
    index.delete_version("bob", "a-new")
    assert index.search("alice", ["a-new"], [1.0, 0.0], 5) == ["new"]
    index.delete_version("alice", "a-new")
    assert index.search("alice", ["a-new"], [1.0, 0.0], 5) == []
