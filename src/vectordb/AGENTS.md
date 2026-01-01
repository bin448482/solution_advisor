# Agent Notes for `src/vectordb/`

Role: Chroma-based vector store wrapper with guardrails.

- `chroma_store.py`: `ChromaStore` initializes persistent Chroma client/collection, upserts RAG docs with embeddings from `M3EEmbedding` (converts list metadata to JSON, stamps `indexed_at`, stores `original_json`), and provides raw `query`.
- Guardrailed search: `query_with_guardrails` applies default project filter, boosts slide/detail pages, computes similarity (`1 - distance`), enforces `tau` threshold, and returns reranked top-N or a guardrail message when too low.
- Maintenance helpers: list/delete by project, collection stats, default project inference; relies on `persist_dir` and `vectordb_collection_name` from settings.
