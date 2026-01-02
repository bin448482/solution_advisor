# Agent Notes for `src/qa/`

Role: QA 引擎 + 监控与缓存中间层。

- `qa_engine.py`: `QAEngine.answer(question, project_name=None, top_k=8, top_n=5, tau=0.5, monitor=None)`；先通过 `QAMonitor` 精确/语义缓存命中，未命中则检索 + LLM 生成。返回结构包含 `answer/sources/status`，并附 `cache_status`/`cache_level`。
- `qa_monitor.py`: JSONL 监控与缓存门面。`logs/qa_sessions/qa_logs_YYYYMMDD.jsonl` 按日滚动；精确缓存写 `logs/qa_sessions/qa_cache.jsonl`，可选语义缓存写入 Chroma collection（默认 `qa_cache`，与 `qa.cache.vectordb_version` 绑定，TTL 默认 7 天）。
- `dialogue_orchestrator.py`: 引导式多轮封装（阶段 3），支持 LLM 澄清/追问 JSON 解析与模板降级、语义去重 + 冷却（默认两轮）、fallback 计数，以及监控字段 `dialogue_phase/graph_node/graph_attempt/repeat_blocked_count/fallback_rate/unanswerable_detected`。
- 配置键（见 `config/settings.example.yaml` → `qa.*`）：`monitor_enabled`、`monitor_sample_rate`、`cache_enabled`、`cache_ttl_days`、`cache_semantic_enabled`、`cache_semantic_threshold`、`cache_collection`、`cache_persist_dir`、`vectordb_version`。
- 入口：`src/scripts/qa_gradio.py`（主 Web UI）与 `src/scripts/qa_cli.py`（备份 CLI）均复用同一引擎。
