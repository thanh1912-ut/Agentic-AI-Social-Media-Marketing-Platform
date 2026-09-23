"""Knowledge normalization, chunking and retrieval."""

from .chunking import CHUNKER_VERSION, KnowledgeChunk, chunk_document, normalize_text
from .interfaces import PersistentKnowledgeRepository, source_context
from .retrieval import InMemoryKnowledgeIndex, RetrievedChunk, filter_relevant_chunks

__all__ = [
    "CHUNKER_VERSION",
    "KnowledgeChunk",
    "chunk_document",
    "normalize_text",
    "InMemoryKnowledgeIndex",
    "RetrievedChunk",
    "filter_relevant_chunks",
    "PersistentKnowledgeRepository",
    "source_context",
]
