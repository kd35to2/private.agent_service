import hashlib
import ntpath
import tempfile
import zipfile
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def safe_name(name: str) -> str:
    name = ntpath.basename(name).strip()
    if (
        not name
        or len(name) > 180
        or Path(name).suffix.lower() not in {".pdf", ".docx", ".txt", ".md"}
    ):
        raise ValueError("仅支持 PDF、DOCX、UTF-8 TXT 或 Markdown 文件，文件名最多 180 字符。")
    return name


def split_content(name: str, content: bytes, size: int, overlap: int) -> list[Document]:
    suffix = Path(name).suffix.lower()
    if suffix in {".txt", ".md"}:
        docs = [Document(page_content=content.decode("utf-8-sig"))]
    else:
        from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("document" + suffix)
            path.write_bytes(content)
            if suffix == ".docx":
                with zipfile.ZipFile(path) as archive:
                    if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                        raise ValueError("文档解压后体积过大。")
                loader = Docx2txtLoader(str(path))
            else:
                loader = PyPDFLoader(str(path))
            docs = loader.load()
    if sum(len(d.page_content) for d in docs) > 5_000_000:
        raise ValueError("提取文本过大，请拆成多个文件。")
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=size, chunk_overlap=overlap, add_start_index=True
    ).split_documents(docs)
    if not chunks:
        raise ValueError("未提取到有效文字；扫描件需要先进行 OCR。")
    for chunk in chunks:
        chunk.metadata["source"] = name
        chunk.metadata.pop("producer", None)
    return chunks


def chunk_id(version_id: str, ordinal: int, text: str) -> str:
    return hashlib.sha256(f"{version_id}:{ordinal}:{text}".encode()).hexdigest()
