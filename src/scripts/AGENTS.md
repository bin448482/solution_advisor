# Agent Notes for `src/scripts/`

Role: CLI entrypoints for QA and vector DB management.

- `qa_cli.py`: Click CLI that loads `Settings`, instantiates `M3EEmbedding` + `ChromaStore` + `LLMClient` + `QAEngine`; options `--question/-q`, `--project/-p`, `--top-k`, `--top-n`, `--tau`, `--config`; prints answer, sources, and status; exits non-zero on config/load errors.
- `vectordb_cli.py`: Click command group wrapping `ChromaStore` for ingest (`import-docs`), batch ingest (`batch-import`), ad-hoc `query`, `stats`, and `delete`; respects config overrides for collection/persist dir and uses `M3EEmbedding` for embeddings.
