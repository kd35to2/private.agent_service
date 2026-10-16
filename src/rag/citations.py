import re

from rag.schemas import SearchResult

CITATION = re.compile(r"\[(\d+)\]")


def validate_answer(text: str, evidence: SearchResult) -> tuple[str, list[dict]]:
    allowed = {r.citation: r for r in evidence.results}
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    used = {int(m.group(1)) for m in CITATION.finditer(text)}
    if not used or not used.issubset(allowed):
        return "已找到相关资料，但本次回答未形成可核查引用。请查看下方原文片段，或重新提问。", [
            r.model_dump() for r in evidence.results
        ]
    return text, [r.model_dump() for r in evidence.results if r.citation in used]
