# Streamlit UI Module - Technical Documentation

## Overview

The UI module provides a web-based interface for the QA system using Streamlit. It enables users to interact with the RAG-based question-answering engine through a browser, with support for project selection, parameter tuning, source citation viewing, and feedback collection.

## Architecture

### Component Structure

```
src/ui/
├── streamlit_app.py    # Main application entry point
└── AGENTS.md           # Operational documentation
```

### Integration Points

**Backend Dependencies:**
- `src.qa.qa_engine.QAEngine` - Core Q&A functionality
- `src.qa.dialogue_orchestrator.DialogueOrchestrator` - Multi-turn dialogue support
- `src.config.Settings` - Configuration management
- `src.vectordb.chroma_store.ChromaStore` - Vector database (indirect via QAEngine)

**Data Sources:**
- `ppt_outputs/<project>/embeddings/rag_documents.json` - Project embeddings
- `config/settings.yaml` - System configuration
- `logs/qa_sessions/feedback_YYYYMMDD.jsonl` - User feedback storage

## Session State Management

Streamlit's `st.session_state` maintains application state across reruns:

```python
{
    "dialogue_state": DialogueState,      # Multi-turn conversation state
    "conversation_history": List[Dict],   # Q&A history with metadata
    "current_project": Optional[str],     # Selected project filter
    "qa_params": Dict[str, Any],          # Retrieval parameters
    "use_orchestrator": bool,             # Dialogue mode toggle
    "qa_engine": QAEngine,                # Cached engine instance
    "orchestrator": DialogueOrchestrator  # Cached orchestrator instance
}
```

**State Lifecycle:**
- Initialized on first page load
- Persists across user interactions (reruns)
- Cleared explicitly via "清空会话" button
- Engine instances cached to avoid repeated initialization

## UI Components

### 1. Sidebar Configuration Panel

**Project Selection:**
- Scans `ppt_outputs/` directory for available projects
- Filters projects with valid `embeddings/rag_documents.json`
- Supports "全部项目" mode for cross-project queries
- Updates `st.session_state.current_project`

**Retrieval Parameters:**
- `top_k` (3-20): Number of documents to retrieve from vector DB
- `top_n` (1-10): Number of documents after reranking
- `tau` (0.0-1.0): Similarity threshold for filtering

**Dialogue Mode Toggle:**
- Checkbox to enable/disable DialogueOrchestrator
- When enabled: provides clarification prompts and follow-up suggestions
- When disabled: direct QAEngine calls

**Session Management:**
- "清空会话" button resets dialogue state and history

### 2. Main Chat Interface

**Conversation Display:**
- Uses `st.chat_message()` for user/assistant bubbles
- Shows cache hit indicators (⚡ icon + cache level)
- Displays source citations in expandable sections
- Renders follow-up suggestions as clickable buttons

**Input Handling:**
- `st.chat_input()` for question entry
- Supports Enter to send, Shift+Enter for newline
- Validates non-empty input

**Loading States:**
- `st.spinner("正在思考...")` during LLM generation
- UI freezes for 2-10 seconds (synchronous mode limitation)

### 3. Source Citation Display

**Format:**
```python
{
    "project": str,           # Project name
    "slide_no": int,          # Slide number
    "page_type": List[str],   # Page type tags
    "level": str,             # "slide" or "project"
    "similarity": float       # Cosine similarity score
}
```

**Rendering:**
- Expandable sections per source
- Displays project, slide number, page type, level
- Shows similarity score as percentage metric

### 4. Feedback Collection

**Feedback Types:**
- 👍 Thumbs up (rating: 1)
- 👎 Thumbs down (rating: -1)
- 💬 Text comment (rating: 0)

**Storage Format (JSONL):**
```json
{
    "ts": "2026-01-04T10:30:00",
    "user_id": "streamlit_user",
    "project": "ChatBI",
    "question": "...",
    "answer_id": "1704358200.123",
    "rating": 1,
    "comment": "..."
}
```

**File Location:** `logs/qa_sessions/feedback_YYYYMMDD.jsonl`

## Dialogue Modes

### Basic Mode (QAEngine)

**Flow:**
```
User Question → QAEngine.answer() → Display Answer + Sources
```

**Response Format:**
```python
{
    "answer": str,
    "sources": List[Dict],
    "status": "success" | "no_context" | "error",
    "cache_status": "hit" | "miss",
    "cache_level": "exact"
}
```

### Guided Mode (DialogueOrchestrator)

**Flow:**
```
User Question → DialogueOrchestrator.answer_with_guidance() →
    Clarify | Answer + Suggestions | Gap Prompt
```

**Response Format:**
```python
{
    "answer": str,
    "sources": List[Dict],
    "status": "success" | "clarify" | "no_context" | "error",
    "dialogue_phase": "clarify" | "gap_prompt" | "follow_up",
    "suggestions": List[str],
    "slot_candidates": Dict[str, List[str]]
}
```

**Clarification UI:**
- Displays slot candidates as button grid
- User clicks to fill slot (e.g., project_name, phase, module)
- State updated and query reprocessed

**Suggestions UI:**
- Rendered as clickable chip buttons below answer
- Clicking auto-fills input box and triggers new query

## Technical Constraints

### MVP Phase (Current Implementation)

**Synchronous Mode:**
- Uses `LLMClient.invoke()` (blocking call)
- UI freezes during LLM generation (2-10 seconds)
- No streaming output
- No "stop generation" capability

**Single-User Deployment:**
- Feedback writes are not thread-safe
- No file locking on JSONL appends
- Suitable for internal/demo use only

**Error Handling:**
- Catches exceptions and displays error messages
- Shows stack trace in code block for debugging
- Handles missing projects gracefully

### Future Enhancements (Phase 2)

**Streaming Support:**
- Requires `LLMClient.generate_stream()` backend method
- Would use `st.write_stream()` or manual placeholder updates
- Enables "stop generation" button via generator interruption

**Multi-User Support:**
- File locking for concurrent feedback writes
- Session-based user identification
- Queue-based logging system

## Configuration

**Environment Variables:**
- `DEFAULT_PROJECT`: Pre-select project on startup
- `UI_ACCESS_TOKEN`: Optional authentication token

**Streamlit Config:**
- Page title: "解决方案顾问 Q&A"
- Layout: wide
- Sidebar: expanded by default

## Error Scenarios

| Scenario | Handling |
| --- | --- |
| No projects found | Display warning + setup instructions |
| Project directory missing | Filter out from dropdown |
| Empty question | Input validation (Streamlit built-in) |
| No retrieval results | Show "未找到相关内容" warning |
| LLM timeout/error | Catch exception, display error + traceback |
| Cache hit | Display ⚡ indicator with cache level |

## Performance Considerations

**Caching:**
- QAEngine and DialogueOrchestrator instances cached in session state
- Avoids repeated Settings loading and model initialization
- Cleared only on session reset

**Lazy Loading:**
- Projects scanned on sidebar render (not on every rerun)
- Embeddings not loaded until query time (handled by QAEngine)

**Memory:**
- Conversation history grows unbounded (cleared manually)
- Consider limiting history length for long sessions

## Security Notes

**Default Configuration:**
- Listens on localhost only (internal access)
- No authentication by default

**Sensitive Data:**
- API keys read from environment (not logged)
- User questions/answers logged to feedback files
- No PII collection beyond user input

**External Exposure:**
- Requires authentication (see AGENTS.md for example)
- Consider reverse proxy with rate limiting
- HTTPS recommended for production

## Testing Strategy

**Manual Testing:**
1. Start app: `streamlit run src/ui/streamlit_app.py`
2. Select project from dropdown
3. Submit 3 test questions
4. Verify: sources displayed, cache indicators, feedback writes

**Edge Cases:**
- No projects available
- Empty/very long questions
- Low similarity results (below tau threshold)
- Network errors / LLM timeouts
- Clarification mode (DialogueOrchestrator)

**Automated Testing:**
- Future: E2E tests with `LLM_PROVIDER=mock`
- Selenium/Playwright for UI interaction testing

## Troubleshooting

**"未找到任何项目":**
- Run PPT pipeline first: `python -m src --input ppts/<file>.pptx --output ppt_outputs/<name>`
- Check `ppt_outputs/` directory exists and contains projects

**UI Freezes:**
- Expected behavior in MVP (synchronous mode)
- Wait 2-10 seconds for LLM response
- Check network connectivity if timeout occurs

**Feedback Not Saved:**
- Check `logs/qa_sessions/` directory exists
- Verify write permissions
- Check disk space

**Cache Not Working:**
- Ensure QAMonitor is enabled in settings
- Check `logs/qa_sessions/qa_cache.jsonl` exists
- Verify cache TTL not expired (7 days default)

## Future Roadmap

**Phase 2 Features:**
- Streaming output with token-by-token display
- Stop generation button
- Multi-user authentication and session management
- Conversation export (JSON/Markdown)
- Advanced analytics dashboard

**Phase 3 Features:**
- Multi-language support
- Voice input/output
- Document upload for ad-hoc queries
- Integration with external knowledge bases
