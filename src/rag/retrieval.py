import re

import jieba
from rank_bm25 import BM25Okapi

IDENTIFIER = re.compile(r"(?<![a-z0-9])[a-z0-9]+(?:[-_./][a-z0-9]+)+(?![a-z0-9])", re.I)


def identifiers(text: str) -> set[str]:
    return {m.group().lower() for m in IDENTIFIER.finditer(text)}


def tokenize(text: str) -> list[str]:
    text = text.lower()
    return [m.group() for m in IDENTIFIER.finditer(text)] + [
        t for t in jieba.lcut(text) if re.search(r"[\w\u4e00-\u9fff]", t)
    ]


def keyword_search(query: str, rows: list, k: int) -> list[str]:
    if not rows:
        return []
    corpus = [tokenize(row.text) for row in rows]
    # BM25Okapi's IDF can be <= 0 for very small corpora. Exact token matching
    # remains a valid lexical candidate even then; fusion uses ranks, not scores.
    terms = tokenize(query)
    scores = BM25Okapi(corpus).get_scores(terms)
    wanted = set(terms)
    candidates = [i for i, tokens in enumerate(corpus) if wanted.intersection(tokens)]
    candidates.sort(key=lambda i: float(scores[i]), reverse=True)
    return [rows[i].chunk_id for i in candidates[:k]]


def fuse(*rankings: list[str]) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(dict.fromkeys(ranking), 1):
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
