"""
RAG Document Generation Package (v2)

This package provides multi-chunk RAG document generation with QA pairs,
LLM-based classification, and multiple chunk types for enhanced retrieval.

Main modules:
- models: Data models (QAPair, ChunkDocument, Category, ChunkMetadata)
- qa_generator: Generate QA pairs from PageSummary
- classifier: LLM-based category classification
- chunk_generator: Multi-type chunk generation (qa/topic/step/metrics/overview)
- legacy: Original single-chunk RAG preparation (deprecated)
"""

# Export main functions and models for convenience
from src.rag.legacy import (
    prepare_slide_embedding,
    prepare_project_embedding,
    clean_summary_for_embedding,
    _classify_page_types,
)

__all__ = [
    "prepare_slide_embedding",
    "prepare_project_embedding",
    "clean_summary_for_embedding",
    "_classify_page_types",
]
