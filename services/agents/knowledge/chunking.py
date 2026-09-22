"""Deterministic chunks for normalized Vietnamese brand documents."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from packages.contracts import NormalizedDocument

TOKEN_RE = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)


def normalize_text(value: str) -> str:
    """Normalize Unicode/whitespace without stripping Vietnamese diacritics."""

    normalized = unicodedata.normalize("NFC", value)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokens(value: str) -> list[str]:
    return TOKEN_RE.findall(normalize_text(value))


def _untokenize(tokens: list[str]) -> str:
    """Readable deterministic reconstruction from tokenizer output."""

    output = ""
    for token in tokens:
        if not output:
            output = token
        elif re.match(r"^[\wÀ-ỹ]", token, flags=re.UNICODE) and output[-1].isalnum():
            output += " " + token
        elif token in {".", ",", ";", ":", "!", "?", "%", ")", "]", "}"}:
            output += token
        elif output[-1] in "([{":
            output += token
        else:
            output += " " + token
    return output


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    company_id: str
    brand_id: str
    source_id: str
    document_id: str
    source_version: str
    source_hash: str
    locator: str
    text: str
    token_count: int
    kind: str = "text"
    active: bool = True
    embedding: tuple[float, ...] | None = None


def _windowed_chunks(
    *,
    text: str,
    heading: str | None,
    base_id: str,
    start_locator: str,
    max_tokens: int,
    overlap_tokens: int,
    make_chunk,
) -> list[KnowledgeChunk]:
    tokens = _tokens(text)
    if not tokens:
        return []

    chunks: list[KnowledgeChunk] = []
    step = max_tokens - overlap_tokens
    for start in range(0, len(tokens), step):
        window = tokens[start : start + max_tokens]
        if not window:
            break
        body = _untokenize(window)
        if heading:
            body = f"{heading}\n{body}"
        chunks.append(make_chunk(body, len(window), f"{start_locator}#chunk-{len(chunks) + 1}"))
        if start + max_tokens >= len(tokens):
            break
    return chunks


def chunk_document(
    document: NormalizedDocument,
    *,
    max_tokens: int = 600,
    overlap_tokens: int = 80,
) -> list[KnowledgeChunk]:
    """Chunk text by block and tables by header + row.

    ``overlap_tokens`` is capped at 80 by contract.  A table row is kept with
    its header so a retrieved row is interpretable without neighboring rows.
    """

    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if not 0 <= overlap_tokens <= 80 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be between 0 and 80 and below max_tokens")

    chunks: list[KnowledgeChunk] = []
    sequence = 0

    def make_chunk(text: str, token_count: int, locator: str, kind: str = "text") -> KnowledgeChunk:
        nonlocal sequence
        sequence += 1
        return KnowledgeChunk(
            chunk_id=(
                f"{document.company_id}:{document.brand_id}:"
                f"{document.source_id}:{document.source_hash}:{sequence}"
            ),
            company_id=document.company_id,
            brand_id=document.brand_id,
            source_id=document.source_id,
            document_id=document.document_id,
            source_version=document.source_version,
            source_hash=document.source_hash,
            locator=locator,
            text=text,
            token_count=token_count,
            kind=kind,
            active=document.active,
        )

    for block in document.text_blocks:
        content = normalize_text(block.text)
        chunks.extend(
            _windowed_chunks(
                text=content,
                heading=normalize_text(block.heading) if block.heading else None,
                base_id=block.block_id,
                start_locator=block.locator,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
                make_chunk=make_chunk,
            )
        )

    for table in document.table_blocks:
        header = " | ".join(normalize_text(item) for item in table.headers)
        for row_index, row in enumerate(table.rows, start=1):
            row_text = " | ".join(normalize_text(item) for item in row)
            table_text = f"Bảng: {header}\nHàng {row_index}: {row_text}"
            row_tokens = _tokens(table_text)
            if len(row_tokens) > max_tokens:
                # A row remains a single semantic unit; truncate only as an
                # explicit warning would be unsafe, so split it deterministically.
                chunks.extend(
                    _windowed_chunks(
                        text=table_text,
                        heading=None,
                        base_id=table.block_id,
                        start_locator=f"{table.locator}[row={row_index}]",
                        max_tokens=max_tokens,
                        overlap_tokens=overlap_tokens,
                        make_chunk=lambda body, count, locator: make_chunk(body, count, locator, "table"),
                    )
                )
            else:
                chunks.append(
                    make_chunk(
                        table_text,
                        len(row_tokens),
                        f"{table.locator}[row={row_index}]",
                        "table",
                    )
                )
    return chunks
