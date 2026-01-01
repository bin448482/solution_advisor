# Source Directory (src/)

This directory contains the core PPT parsing and project profiling pipeline implementation.

## Overview

The src/ directory implements a complete pipeline that transforms PowerPoint presentations into structured, traceable project profiles suitable for RAG-based Q&A systems.

## Module Organization

```
src/
├── models.py              # Pydantic data models (SlideText, PageSummary, ProjectProfile, Manifest)
├── config.py              # YAML-based configuration (Settings class)
├── utils.py               # Utilities (hashing, JSON I/O, command execution, data URLs)
├── rag.py                 # RAG document preparation (embedding-ready docs)
├── pipeline.py            # Main orchestration (PPTPipeline class)
├── __main__.py            # CLI entry point
├── renderer/              # PPTX → PNG conversion (see renderer/CLAUDE.md)
├── extractor/             # Text extraction from PPTX (see extractor/CLAUDE.md)
└── summarizer/            # LLM-based analysis (see summarizer/CLAUDE.md)
```

## Core Components

### models.py

Defines all data structures using Pydantic for validation and serialization:

**`SlideText`**: Extracted text from a single slide
- Fields: slide_no, title, text_content, notes

**`PageSummary`**: LLM-generated summary of a single slide
- Fields: slide_no, title, one_liner, bullets, details, image_caption, entities, signals, evidence, confidence

**`ProjectProfile`**: Aggregated profile across all slides
- Fields: project_name, positioning, target_users, core_value, core_capabilities, architecture, deployment, integrations, differentiators, cases, risks_and_limits, open_questions, evidence_map

**`Manifest`**: Pipeline execution metadata
- Fields: input_file, file_hash, timestamp, page_count, errors, duration_seconds, output_dir, provider, model, page_summaries, rag_documents

### config.py

YAML-based configuration system:

**`Settings`** class:
- LLM configuration: provider, api_key, base_url, model, temperature
- Rendering: render_dpi, libreoffice_path, pdftoppm_path
- Processing: max_workers (for parallel summarization)

**Loading**:
```python
settings = Settings.from_yaml("config/settings.yaml")
settings = settings.with_overrides(llm_model="gpt-4o")  # Runtime overrides
```

**Default Path**: `config/settings.yaml` (gitignored)
**Template**: `config/settings.example.yaml` (committed)

### utils.py

Common utilities used across modules:

**File Operations**:
- `compute_sha256(path)`: Hash PPTX for idempotency checks
- `save_json(data, path)`: Write JSON with pretty formatting
- `load_json(path)`: Read JSON with error handling
- `ensure_dir(path)`: Create directory if not exists

**Command Execution**:
- `run_command(cmd, timeout)`: Execute shell commands with timeout
- Used by renderer for LibreOffice/Poppler

**Data Encoding**:
- `image_to_data_url(path)`: Convert PNG to base64 data URL
- Used by summarizer for LLM vision input

### rag.py

Prepares embedding-ready documents for vector databases:

**`prepare_slide_embedding(project_name, summary)`**:
- Converts PageSummary to semantic text + metadata
- ID format: `{project_name}_slide_{slide_no:03d}`
- Level: "slide" (detail)

**`prepare_project_embedding(project_name, profile)`**:
- Converts ProjectProfile to overview document
- ID format: `{project_name}_overview`
- Level: "project" (overview)

**`clean_summary_for_embedding(summary)`**:
- Unnests JSON-like content in details/bullets
- Strips `<think>...</think>` blocks
- Flags suspicious content for review
- Returns: (cleaned_summary, issues)

**Integration**: Called by pipeline.py after profile generation (pipeline.py:90-113)

### pipeline.py

Main orchestration logic:

**`PPTPipeline`** class:
- Coordinates all pipeline stages
- Handles errors gracefully (continue on single-slide failures)
- Writes manifest with metadata and errors

**Pipeline Stages**:
1. **Idempotency Check**: Compare PPTX hash with previous run
2. **Rendering**: PPTX → PNG images (sequential)
3. **Text Extraction**: PPTX → SlideText objects (fast)
4. **Page Summarization**: Images + text → PageSummary objects (parallel)
5. **Profile Generation**: Summaries → ProjectProfile (sequential)
6. **RAG Preparation**: Summaries + profile → embedding docs (fast)
7. **Manifest Writing**: Metadata + errors → manifest.json

**Error Collection**:
- Errors recorded with stage, slide_no, error message
- Processing continues when possible
- Manifest includes all errors for review

### __main__.py

CLI entry point:

**Usage**:
```bash
python -m src --input ppts/file.pptx --output ppt_outputs/file [--force] [--verbose]
```

**Arguments**:
- `--input`: Path to input PPTX file (required)
- `--output`: Output directory (required)
- `--config`: Config file path (default: config/settings.yaml)
- `--force`: Force re-run (ignore hash check)
- `--verbose`: Enable debug logging

## Data Flow

```
PPTX Input
  ↓
[Renderer] → slides/*.png + intermediate PDF
  ↓
[Extractor] → List[SlideText] (in-memory)
  ↓
[PageSummarizer] → page_summaries/*.json (parallel)
  ↓
[ProfileGenerator] → doc_summary/project_profile.json
  ↓
[RAGPreparer] → embeddings/rag_documents.json
  ↓
[Pipeline] → manifest.json
```

## Configuration

**Required Settings**:
- `llm_provider`: "openai" | "anthropic" | "local" | "mock"
- `llm_api_key`: API key (not needed for mock)
- `llm_model`: Model name

**Optional Settings**:
- `llm_base_url`: Custom endpoint
- `llm_temperature`: 0.0-1.0 (default: 0.1)
- `render_dpi`: Image resolution (default: 150)
- `max_workers`: Parallel summarization (default: 3)
- `libreoffice_path`: Path to soffice (default: "soffice")
- `pdftoppm_path`: Path to pdftoppm (default: "pdftoppm")

**Mock Mode**: Set `llm_provider: mock` for testing without API calls

## Error Handling

**Fail Fast**:
- Missing dependencies (LibreOffice, Poppler)
- Invalid configuration
- Missing input file

**Continue on Error**:
- Single slide rendering failure
- Single slide summarization failure
- RAG preparation issues

**Error Recording**:
- All errors collected in manifest.json
- Includes: stage, slide_no (if applicable), error message
- Enables post-processing review and debugging

## Common Tasks

### Running the Pipeline

```bash
# Basic run
python -m src --input ppts/demo.pptx --output ppt_outputs/demo

# Force re-run (ignore cache)
python -m src --input ppts/demo.pptx --output ppt_outputs/demo --force

# With custom config
python -m src --input ppts/demo.pptx --output ppt_outputs/demo --config my_config.yaml

# Verbose logging
python -m src --input ppts/demo.pptx --output ppt_outputs/demo --verbose
```

### Testing Without API

```yaml
# config/settings.yaml
llm_provider: mock
llm_model: mock-model
```

This enables full pipeline testing without external API calls.

### Debugging Pipeline Issues

1. Check manifest.json for errors
2. Inspect intermediate outputs (slides/, page_summaries/)
3. Use --verbose for detailed logging
4. Test individual modules in isolation

### Adding New Pipeline Stages

1. Implement stage logic in new module
2. Add stage to PPTPipeline.run()
3. Update manifest schema if needed
4. Add error handling with stage marker
5. Update tests

## Testing

**Unit Tests**: `tests/test_models.py` (Pydantic models)
**Integration Tests**: `tests/test_pipeline_e2e.py` (full pipeline with mock LLM)

**Test Requirements**:
- LibreOffice (soffice) and Poppler (pdftoppm) for rendering
- Sample PPTX: `ppts/ChatBI产品介绍_2025.pptx`
- Mock LLM mode for offline testing

## Dependencies

**Python Libraries**:
- pydantic: Data validation and serialization
- python-pptx: PPTX text extraction
- langchain: LLM abstraction
- openai/anthropic: LLM providers
- pillow: Image processing
- pyyaml: Configuration parsing

**External Executables**:
- LibreOffice (soffice): PPTX → PDF conversion
- Poppler (pdftoppm): PDF → PNG conversion

## Future Enhancements

- Streaming pipeline (process slides as they're rendered)
- Distributed processing (multiple workers across machines)
- Incremental updates (only process changed slides)
- Alternative renderers (direct Python libraries)
- Multi-language support (auto-detect and adapt prompts)
- Quality metrics (automatic evaluation of summaries)
