import io
import zipfile

import pytest

from rag.splitting import safe_name, split_content


def test_word_chunks_have_real_text_offsets_without_fabricated_pages():
    buffer = io.BytesIO()
    text = "投标方案：系统配置。" * 500
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
            + text
            + "</w:t></w:r></w:p></w:body></w:document>",
        )
    chunks = split_content("方案.docx", buffer.getvalue(), 2000, 500)
    assert len(chunks) > 1
    for chunk in chunks:
        assert "page" not in chunk.metadata
        start = chunk.metadata["start_index"]
        assert text[start : start + len(chunk.page_content)] == chunk.page_content
        assert len(chunk.page_content) <= 2000
        assert chunk.metadata["source"] == "方案.docx"


def test_unsupported_or_empty_documents_are_not_indexed():
    assert safe_name("../../方案.docx") == "方案.docx"
    with pytest.raises(ValueError):
        safe_name("data.exe")
    with pytest.raises(ValueError):
        split_content("empty.txt", b"   ", 2000, 500)
