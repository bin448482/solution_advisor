# Agent Notes for `src/scripts/`

Role: CLI entrypoints for QA and vector DB management.

- `qa_cli.py`: Click CLI that loads `Settings`, instantiates `M3EEmbedding` + `ChromaStore` + `LLMClient` + `QAEngine` + `QAMonitor`; options `--question/-q`, `--project/-p`, `--top-k`, `--top-n`, `--tau`, `--config`; prints answer, sources, status，并在缓存命中时显示 `[cache hit/<level>]`。
- `qa_gradio.py`: Gradio Web UI（主推荐入口）复用同一 QAEngine + DialogueOrchestrator；参数 `--config/--host/--port/--project`，按钮式追问 + 来源展示，适合演示/运营。
- `vectordb_cli.py`: Click command group wrapping `ChromaStore` for ingest (`import-docs`), batch ingest (`batch-import`), ad-hoc `query`, `stats`, and `delete`; respects config overrides for collection/persist dir and uses `M3EEmbedding` for embeddings.
- `qa_eval_llm.py`: 读取 `tests/qa_test_results/qa_test_*.json`（或指定文件），用 LLM 自评问答质量并输出 `qa_eval_*.json`；支持 `--eval-provider/--eval-model/--limit` 覆盖配置，默认温度 0。
