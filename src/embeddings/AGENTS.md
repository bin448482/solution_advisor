# Agent Notes for `src/embeddings/`

Role: M3E Chinese embedding wrapper for downstream RAG components.

- `m3e_model.py`: `M3EEmbedding` downloads/caches SentenceTransformer models (m3e-base/-large) to `models/`, selects device (CPU/CUDA/MPS) with safe fallback to CPU, exposes `embed_texts` batching with tqdm + OOM retry plus `embed_single` and `dimension`.
- Dependencies: `torch`, `sentence_transformers`; ensure GPU drivers match the requested device when running on CUDA/MPS.
