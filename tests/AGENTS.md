# Agent Notes for `tests/`

- `test_models.py`: sanity checks for Pydantic models (Manifest, ProjectProfile, PageSummary).
- `test_pipeline_e2e.py`: smoke test that runs the pipeline on `ppts/ChatBI产品介绍_2025.pptx` with `LLM_PROVIDER=mock`; skipped if sample PPT or `soffice`/`pdftoppm` missing.
