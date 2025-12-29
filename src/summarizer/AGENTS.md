# Agent Notes for `src/summarizer/`

Role: LLM-based summarization and profiling.

- `llm_client.py`: wraps LangChain chat models (OpenAI/Anthropic/local); `LLM_PROVIDER=mock` returns prompt for offline use; supports optional vision via image data URL.
- `page_summarizer.py`: builds Chinese JSON prompt per slide, fuses text + optional image, parses model output with fallbacks, returns `PageSummary`.
- `profile_generator.py`: aggregates page summaries into `ProjectProfile` via LLM or mock heuristic.
- `__init__.py`: re-exports main classes.
