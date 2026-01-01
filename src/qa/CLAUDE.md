# QA Module (src/qa/)

Provides a thin orchestration layer that turns retrieved Chroma results into a single LLM answer for user questions, with pluggable monitoring + caching (QAMonitor).

## Components

- **QAEngine (qa_engine.py)**  
  - Constructor expects `ChromaStore`, `LLMClient`, and optional `QAMonitor`.  
  - `answer(question, project_name=None, top_k=8, top_n=5, tau=0.5)`:
    1) 尝试 `QAMonitor` 精确/语义缓存命中（默认启用，TTL=7d，绑定 `qa.cache.vectordb_version`）。  
    2) 未命中则调用 `store.query_with_guardrails`，重排后构建上下文。  
    3) 调用 LLM 生成回答，返回 `{answer, sources, status, cache_status?, cache_level?}`；监控日志写入 `logs/qa_sessions/qa_logs_YYYYMMDD.jsonl`。
- **QAMonitor (qa_monitor.py)**  
  - JSONL 日志 + 本地精确缓存（`qa_cache.jsonl`）；可选语义缓存写入 Chroma collection `qa_cache`。  
  - 主要方法：`normalize_question`、`build_question_id`、`get_cache`、`save_cache`, `log_event`.

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

qa = QAEngine(store, llm, monitor=QAMonitor(settings, embedding))
result = qa.answer("ChatBI的核心功能是什么", project_name="ChatBI")
```

- Returned `status` values: `success` (answer + sources), `no_context` (nothing above `tau`), `error` (LLM/retrieval failure with `error` message).
- `sources` entries include `project`, `slide_no`, `level`, and `similarity` for UI display; `cache_status/cache_level` 标识命中信息。

## Operational Notes

- Depends on Chroma collection already populated (e.g., via `scripts/vectordb_cli.py import-docs`).
- `top_k/top_n/tau` defaults mirror the guardrail settings used by QA CLI; keep them aligned with product expectations.
- Monitoring: `qa.monitor_enabled` + `monitor_sample_rate` 控制是否写 JSONL；CLI 可用默认配置即可查看命中/耗时。
- LLM errors are swallowed into `status: error` so upstream callers should log/alert accordingly.
