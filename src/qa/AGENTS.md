# Agent Notes for `src/qa/`

Role: Lightweight QA engine combining Chroma retrieval with LLM generation.

- `qa_engine.py`: `QAEngine.answer(question, project_name=None, top_k=8, top_n=5, tau=0.5)` runs `ChromaStore.query_with_guardrails`, normalizes results into `[文档N]` context blocks, builds a Chinese prompt that forbids fabrication, and calls `LLMClient.generate`.
- Guardrails: empty/low-similarity retrieval → `status: no_context`; retrieval/LLM failures → `status: error` with message; successful responses return `answer`, `sources` (project/slide/level/similarity), and `status: success`.
