# Repository Guidelines

This repository is currently **document- and asset-driven**: it stores project PPTs and design/requirements docs, plus generated snapshot outputs.

## Project Structure & Module Organization

- `docs/`: Source-of-truth documentation (requirements, designs, notes). Prefer Markdown (`.md`).
- `ppts/`: Input PPT/PPTX assets (e.g. `ppts/ChatBI产品介绍_2025.pptx`).
- `ppt_outputs/`: Generated outputs (slide images, per-page summaries, manifests). Treat as build artifacts unless explicitly needed for review.
- `.claude/`: Local agent/tool settings (keep minimal; avoid committing secrets).

If you add executable code, introduce clear top-level directories:
- `src/` for implementation, `tests/` for automated tests, `scripts/` for CLI utilities.

## Build, Test, and Development Commands

There is **no build/test runner committed yet**. Common repo checks:

- `git status` — confirm only intended files are staged/modified.
- `find docs -name "*.md" -maxdepth 1` — list key docs for review.
- `ls -la ppts ppt_outputs` — verify inputs vs generated artifacts.

When adding an automation pipeline (PPT→images→summaries), provide a single entrypoint, e.g. `python -m <module> --input ppts/... --out ppt_outputs/...`.

## Coding Style & Naming Conventions

- Prefer consistent, descriptive naming:
  - PPT inputs: `ppts/<ProjectName>_<Year>.pptx`
  - Snapshot outputs: `ppt_outputs/<ppt_basename>/slides/001.png`
  - Docs: `docs/<Topic>.md`
- Keep Markdown concise and scannable: short sections, bullet lists, and explicit file paths.

## Testing Guidelines

- If code is added, include basic tests in `tests/` and document how to run them in this file.
- Add at least one “smoke test” that validates the end-to-end pipeline on a small PPT sample.
- Embedding回归：`tmp_run_tests.py` / `ChromaStore.query_with_guardrails` 默认 project 过滤 + Top-K=8 召回、细节页/slide 加分重排 + 0.5 相似度阈值，生成 `tmp_embedding_test_round1.json` 供对比。

## Commit & Pull Request Guidelines

- Git history uses short, direct commit messages (often Chinese), e.g. “保存…/更新…”. Keep messages **1 line**, describing the change intent.
- PRs should include:
  - A brief description of what changed and why
  - Links to relevant docs under `docs/`
  - Notes on any generated artifacts under `ppt_outputs/` (and whether they should be committed)

## Security & Configuration Tips

- Do not commit API keys, tokens, or customer-sensitive content.
- If `ppt_outputs/` is treated as generated output, add/update `.gitignore` accordingly.

## Code status (MVP skeleton)
- Python pipeline lives in `src/` with CLI entry `python -m src --input ppts/... --output ppt_outputs/... --force`.
- Core pieces: rendering (`renderer/libreoffice.py`), text extraction (`extractor/ppt_extractor.py`), LLM summarization (`summarizer/`), orchestration (`pipeline.py`), config (`config.py`), CLI (`__main__.py`), utilities (`utils.py`).
- RAG 文档生成：`rag.py` + `pipeline.py` 将单页/画像转换为 `ppt_outputs/<ppt>/embeddings/rag_documents.json`，同时在 manifest 中记录 `rag_documents` 数量。
- Tests under `tests/` include model sanity and an e2e smoke that requires `soffice` + `pdftoppm` and uses `LLM_PROVIDER=mock`.
- Dependencies listed in `requirements.txt`; config template in `config/settings.example.yaml`; usage in `README.md`.
