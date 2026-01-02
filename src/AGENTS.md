# Agent Notes for `src/`

Purpose: Python MVP pipeline turning PPT → slide images → page summaries → project profile → manifest.

Key modules:
- `config.py`: env-driven `Settings` (LLM provider/api key/model, render tools, workers, DPI) + RAG feature toggles `enable_llm_classify/topic/step/metrics`（默认关，控制分类与可选 chunk 生成）。
- `pipeline.py`: orchestrates render → extract → per-page summarize (threaded) → profile → RAG chunk 生成（尊重上述开关；refine 复用同一逻辑）；writes manifest and JSON outputs.
- `qa/qa_monitor.py`: 监控与缓存门面，JSONL 日志 + 精确缓存（内存索引 + `logs/qa_sessions/qa_cache.jsonl`，TTL 默认 7 天，绑定 `qa.cache.vectordb_version`）；语义缓存已移除；`qa_engine.py` 可注入。
- `qa/dialogue_orchestrator.py`: 引导式对话封装（LangGraph + 模板 gap/follow-up），供 Gradio/CLI 复用。
- `utils.py`: hashing, JSON IO, command runner, data URL encoding, path helpers.
- `__main__.py`: CLI `python -m src --input <pptx> --output <dir> [--force] [-v]`.
- `scripts/qa_gradio.py`: Gradio Web UI 入口（按钮式追问，支持项目过滤）。

Dependencies: LibreOffice `soffice`, Poppler `pdftoppm`; LangChain + providers (OpenAI/Anthropic/local), python-pptx, Pillow, pydantic. Set via `.env` or CLI overrides; `LLM_PROVIDER=mock` enables offline summaries.
