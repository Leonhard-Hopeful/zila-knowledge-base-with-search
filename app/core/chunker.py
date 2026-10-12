import re
from dataclasses import dataclass

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from app.core.parsers import Section


@dataclass
class Chunk:
    text: str
    page: int | None
    section: str | None


def _splitter(size: int, overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def pick_params(sections: list[Section], kind: str,
                size: int | None, overlap: int | None) -> tuple[int, int]:
    """Heuristic defaults; explicit values from the upload win."""
    if size:
        ov = overlap if overlap is not None else size // 8
        return size, max(0, min(ov, size - 1))   # overlap must be < size
    avg_len = sum(len(s.text) for s in sections) / max(len(sections), 1)
    if kind == "markdown":
        return 400, 50
    if avg_len < 800:          # slide decks: short pages, keep them intact
        return 250, 30
    return 450, 60             # long-form notes


def chunk_document(sections: list[Section], kind: str,
                   size: int | None = None, overlap: int | None = None) -> list[Chunk]:
    size, overlap = pick_params(sections, kind, size, overlap)
    splitter = _splitter(size, overlap)
    chunks: list[Chunk] = []

    if kind == "markdown":
        md = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        )
        for doc in md.split_text(sections[0].text):
            heading = " > ".join(
                doc.metadata[k] for k in ("h1", "h2", "h3") if k in doc.metadata
            )
            for piece in splitter.split_text(doc.page_content):
                chunks.append(Chunk(_clean(piece), None, heading or None))
    else:
        for sec in sections:
            if not sec.text.strip():
                continue
            for piece in splitter.split_text(sec.text):
                chunks.append(Chunk(_clean(piece), sec.page, None))

    return [c for c in chunks if len(c.text) > 30]   # drop junk fragments


def _clean(t: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", t).strip()
