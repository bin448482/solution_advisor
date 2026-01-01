# Agent Notes for `tests/`

- `test_models.py`: sanity checks for Pydantic models (Manifest, ProjectProfile, PageSummary).
- `test_pipeline_e2e.py`: smoke test that runs the pipeline on `ppts/ChatBI产品介绍_2025.pptx` with `LLM_PROVIDER=mock`; skipped if sample PPT or `soffice`/`pdftoppm` missing.
- `test_qa_monitor.py`: 单元测试监控/缓存（精确命中、过期失效、日志写入）。
- `test_qa_cli_cache_smoke.py`: QA CLI 冒烟测试（用 monkeypatch 注入 stub 依赖），验证命中提示输出 `[cache hit/<level>]`。
- `tmp_run_tests.py`: embedding 回归/护栏验证脚本，运行后在同目录生成 `tmp_embedding_test_round1.json` 供调参对比。
