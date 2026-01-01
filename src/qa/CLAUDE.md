# QA Module (src/qa/)

Provides a thin orchestration layer that turns retrieved Chroma results into a single LLM answer for user questions.

## Components

- **QAEngine (qa_engine.py)**  
  - Constructor expects an initialized `ChromaStore` and `LLMClient`.  
  - `answer(question, project_name=None, top_k=8, top_n=5, tau=0.5)`:
    1) Calls `store.query_with_guardrails` (project filter + detail-page boost + similarity gate).  
    2) Normalizes results into readable context blocks `[文档N] 项目: <name>, 页码: <n>` and captures source metadata.  
    3) Builds a Chinese prompt that forbids fabrication and instructs citing slide numbers; returns structured dict `{answer, sources, status, error?}`.

## Prompt (summary)

```
你是专业解决方案顾问，只能使用检索到的文档；若无信息需说“文档中未提及”；回答时自然提及来源（如“根据第X页…”）。
```

## Typical Usage

```python
from src.embeddings import M3EEmbedding
from src.vectordb import ChromaStore
from src.summarizer import LLMClient
from src.qa import QAEngine
from src.config import Settings

settings = Settings.from_yaml("config/settings.yaml")
embedding = M3EEmbedding(settings.embedding_model, settings.embedding_device, settings.embedding_cache_dir)
store = ChromaStore(settings.vectordb_persist_dir, settings.vectordb_collection_name, embedding)
llm = LLMClient(settings)

qa = QAEngine(store, llm)
result = qa.answer("ChatBI的核心功能是什么", project_name="ChatBI")
```

- Returned `status` values: `success` (answer + sources), `no_context` (nothing above `tau`), `error` (LLM/retrieval failure with `error` message).
- `sources` entries include `project`, `slide_no`, `level`, and `similarity` for UI display.

## Operational Notes

- Depends on Chroma collection already populated (e.g., via `scripts/vectordb_cli.py import-docs`).
- `top_k/top_n/tau` defaults mirror the guardrail settings used by QA CLI; keep them aligned with product expectations.
- LLM errors are swallowed into `status: error` so upstream callers should log/alert accordingly.
