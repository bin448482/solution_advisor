# Agent Notes for `src/`

Purpose: Python MVP pipeline turning PPT → slide images → page summaries → project profile → manifest.

Key modules:
- `config.py`: env-driven `Settings` (LLM provider/api key/model, render tools, workers, DPI).
- `pipeline.py`: orchestrates render → extract → per-page summarize (threaded) → profile; writes manifest and JSON outputs.
- `utils.py`: hashing, JSON IO, command runner, data URL encoding, path helpers.
- `__main__.py`: CLI `python -m src --input <pptx> --output <dir> [--force] [-v]`.

Dependencies: LibreOffice `soffice`, Poppler `pdftoppm`; LangChain + providers (OpenAI/Anthropic/local), python-pptx, Pillow, pydantic. Set via `.env` or CLI overrides; `LLM_PROVIDER=mock` enables offline summaries.
