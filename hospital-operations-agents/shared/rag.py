"""Small, deterministic document RAG implementation with source citations."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from shared.config import DOCUMENTS_DIR

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
TENANT_HEADER = re.compile(r"^\[TENANT:(ALL|HOSP-[A-Z])\]\s*$")


@dataclass(frozen=True)
class DocumentChunk:
    source: str
    chunk_id: int
    tenant_id: str
    text: str

    @property
    def citation(self) -> str:
        return f"{self.source}#chunk-{self.chunk_id}"


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.casefold())


def _split_text(text: str, *, max_chars: int = 480, overlap_chars: int = 80) -> list[str]:
    """Create bounded overlapping chunks without external services."""
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            overlap = current[-overlap_chars:].lstrip()
            current = f"{overlap}\n\n{paragraph}".strip()
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def load_documents(documents_dir: Path | str = DOCUMENTS_DIR) -> list[DocumentChunk]:
    """Load text files and preserve per-section tenant metadata."""
    chunks: list[DocumentChunk] = []
    for path in sorted(Path(documents_dir).glob("*.txt")):
        if path.is_symlink() or not path.is_file():
            continue
        tenant = "ALL"
        section_lines: list[str] = []
        sections: list[tuple[str, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            match = TENANT_HEADER.match(line.strip())
            if match:
                if section_lines:
                    sections.append((tenant, "\n".join(section_lines).strip()))
                tenant = match.group(1)
                section_lines = []
            else:
                section_lines.append(line)
        if section_lines:
            sections.append((tenant, "\n".join(section_lines).strip()))
        chunk_number = 1
        for section_tenant, section_text in sections:
            for text in _split_text(section_text):
                chunks.append(DocumentChunk(path.name, chunk_number, section_tenant, text))
                chunk_number += 1
    return chunks


def _cosine_similarity(query: str, text: str) -> float:
    query_counts, text_counts = Counter(_tokens(query)), Counter(_tokens(text))
    if not query_counts or not text_counts:
        return 0.0
    dot = sum(count * text_counts[token] for token, count in query_counts.items())
    q_norm = math.sqrt(sum(count * count for count in query_counts.values()))
    t_norm = math.sqrt(sum(count * count for count in text_counts.values()))
    return dot / (q_norm * t_norm) if dot else 0.0


def search_documents(
    query: str,
    *,
    tenant_id: str | None = None,
    documents_dir: Path | str = DOCUMENTS_DIR,
    top_k: int = 3,
) -> list[dict]:
    """Retrieve relevant chunks and include stable, human-readable citations."""
    candidates = load_documents(documents_dir)
    if tenant_id is not None:
        candidates = [chunk for chunk in candidates if chunk.tenant_id in {"ALL", tenant_id}]
    ranked = sorted(
        ((_cosine_similarity(query, chunk.text), chunk) for chunk in candidates),
        key=lambda item: (-item[0], item[1].citation),
    )
    matches = [(score, chunk) for score, chunk in ranked if score > 0][:top_k]
    return [
        {
            "text": chunk.text,
            "source": chunk.source,
            "citation": chunk.citation,
            "tenant_id": chunk.tenant_id,
            "score": round(score, 4),
        }
        for score, chunk in matches
    ]
