# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains two interconnected systems for solution advisory:

1. **PPT Parsing & Project Profiling Pipeline**: Converts project PPTs into structured, traceable project profiles
2. **External Consulting Agent**: RAG-based Q&A system for customer-facing inquiries (future component)

The primary focus is the PPT parsing pipeline, which extracts slides as images, generates per-page summaries using multimodal LLMs, and aggregates them into comprehensive project profiles.

## Development Commands

### Running the PPT Pipeline

```bash
# Basic usage
python -m src --input ppts/ChatBI产品介绍_2025.pptx --output ppt_outputs/ChatBI产品介绍_2025

# Force re-run (ignore cached results)
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --force

# Verbose logging
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --verbose
```

### Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_pipeline_e2e.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/
```

## Architecture Overview

### PPT Pipeline Data Flow

```
PPTX Input
  ↓
[Renderer] LibreOffice headless: PPTX → PDF → PNG images
  ↓
[Extractor] python-pptx: Extract titles, text boxes, speaker notes
  ↓
[PageSummarizer] LLM Vision API: Image + text → structured JSON summary (parallel)
  ↓
[ProfileGenerator] LLM: Aggregate summaries → project profile with evidence map
  ↓
[RAGPreparer] Slide-level + project-level docs → embeddings/rag_documents.json
  ↓
[Pipeline] Write manifest.json with metadata and errors
```

### Key Architectural Decisions

**Rendering Strategy**: Two-step conversion (PPTX → PDF → PNG) via LibreOffice headless provides better reliability than direct conversion. The intermediate PDF is kept for debugging.

**Text Enhancement**: Combines visual analysis (LLM Vision API on slide images) with extracted text (titles, content, speaker notes) to reduce hallucination and improve accuracy.

**Error Handling Philosophy**:
- Critical errors (missing dependencies, invalid config) → fail fast
- Single-page errors → continue processing, collect errors in manifest
- LLM API errors → retry 3x with exponential backoff

**Idempotency**: Uses SHA256 hash of input PPTX stored in manifest.json. Re-runs skip rendering if hash unchanged (override with `--force`).

**Parallelization**:
- Slide rendering: sequential (LibreOffice limitation)
- Page summarization: parallel (configurable via MAX_WORKERS)
- Profile generation: sequential (requires all summaries)

### Module Structure

```
src/
├── models.py              # Pydantic schemas (SlideText, PageSummary, ProjectProfile, Manifest)
├── config.py              # Environment-based configuration (API keys, paths, limits)
├── utils.py               # File hashing, path handling
├── renderer/
│   ├── base.py           # Abstract Renderer interface
│   └── libreoffice.py    # LibreOffice implementation
├── extractor/
│   └── ppt_extractor.py  # python-pptx text extraction
├── summarizer/
│   ├── llm_client.py     # LLM API wrapper (OpenAI-compatible)
│   ├── page_summarizer.py    # Single page → PageSummary
│   └── profile_generator.py  # All summaries → ProjectProfile
├── pipeline.py           # Main orchestration (PPTPipeline class)
└── __main__.py          # CLI entry point
```

### Output Structure

```
ppt_outputs/<ppt_basename>/
├── slides/
│   ├── 001.png, 002.png, ...
├── page_summaries/
│   ├── 001.json, 002.json, ...
├── doc_summary/
│   └── project_profile.json
├── embeddings/
│   └── rag_documents.json
└── manifest.json
```

**manifest.json** contains: input file hash, timestamp, page count, processing duration, and error list (slide_no, stage, error message).

**Noise handling & RAG prep**
- PageSummarizer accepts dict or list JSON responses and captures optional `image_caption` for visual grounding.
- RAG step auto-unnests JSON-looking `details`, flags noisy bullets into `manifest.errors` (stage: `rag_clean`), and records `rag_documents` count.

## Configuration

Configuration now comes from YAML (no .env):
```
config/settings.yaml  # gitignored real config
config/settings.example.yaml  # template with placeholders
```
CLI flag `--config` overrides the path; otherwise defaults to `config/settings.yaml`.

## Data Models (Pydantic)

**PageSummary** fields:
- `slide_no`, `title`, `one_liner` (≤30 chars)
- `bullets` (3-7 items), `details` (1-2 paragraphs)
- `entities` (products, modules, customers, metrics)
- `signals` (page type: positioning, architecture, features, cases, etc.)
- `evidence` (at minimum: slide_no)
- `confidence` (0-1, low confidence flags for manual review)

**ProjectProfile** fields:
- Core: `project_name`, `positioning`, `target_users`, `core_value`, `core_capabilities`
- Technical: `architecture`, `deployment`, `integrations`
- Competitive: `differentiators`, `cases`
- Boundaries: `risks_and_limits`, `open_questions`
- **`evidence_map`**: Maps each field to source slide numbers (critical for traceability)

## Prompt Engineering

**Language**: All prompts use Chinese instructions for Chinese-language PPTs.

**Output Format**: Prompts explicitly specify JSON schema with examples to ensure structured output.

**Confidence Scoring**: Prompts instruct the model to assign confidence scores and flag uncertain extractions.

**Evidence Requirement**: Profile generation prompts emphasize citing slide numbers for every claim.

## Repository Conventions

**Commit Messages**: Use short, direct Chinese messages (1 line), e.g., "实现渲染模块", "修复单页总结错误处理".

**File Naming**:
- Input PPTs: `ppts/<ProjectName>_<Year>.pptx`
- Output snapshots: `ppt_outputs/<ppt_basename>/`
- Docs: `docs/<Topic>.md`

**Generated Artifacts**: `ppt_outputs/` is treated as build artifacts. Update `.gitignore` if these should not be committed.

## External Consulting Agent (Future)

The second system (documented in `docs/对外咨询Agent总体设计.md`) will build on the PPT parsing pipeline:

- **Purpose**: RAG-based Q&A for customer-facing inquiries
- **Integration**: Uses project profiles and document chunks from PPT pipeline as knowledge base
- **Key Principles**: Evidence-based responses only, permission-controlled access, full audit trail
- **Architecture**: OpenAgents orchestration + hybrid search (full-text + vector) + metadata filtering

When implementing the consulting agent, ensure:
- All responses include source citations (doc name + version + page number)
- Permission checks filter by project_id and partner_id before retrieval
- Sensitive topics (pricing, timelines, roadmaps, internal links) default to human handoff
