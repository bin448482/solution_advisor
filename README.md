# Solution Advisor · PPT Parsing & Project Profiling Pipeline

Automatically converts project-introduction PPTs into a structured project profile and a RAG-ready knowledge base. By default, it produces a high-quality `rag_documents.json` centered on **`category_summary` + `overview`**, with an optional LangGraph Map-Reduce path for automated draft generation.

> Project type: AI / Tool / CLI / Web App  
> Primary language: Python 3.9+  
> Tech stack: LibreOffice, Poppler, LangChain/LangGraph, Chroma, M3E, LLM (mockable), Streamlit  
> Target users: Developers / Internal Teams / Solution Consultants

---

## AI-Assisted Quickstart (Claude / Codex)

This project is an **AI-driven pipeline for project ingestion and knowledge distillation**. The end-to-end flow (PPT parsing → summarization → profiling → RAG assets) is documented across `docs/`, module-level `AGENTS.md`, and the code under `src/`. You can use **Claude / Codex** as a “repo guide” to build a working understanding without reading everything end-to-end.

High-frequency prompts you can copy into your assistant:
- “In one sentence: what problem does this repo solve? What are the end-to-end input/output artifacts?”
- “Starting from `python -m src --input ppts/... --output ppt_outputs/...`, explain step-by-step what happens, where outputs go, and how to rerun/force rerun.”
- “Explain the RAG artifact format for `category_summary + overview`, why it’s more stable than per-slide QA, and where the config toggles are.”
- “To onboard a new project: what dependencies and configs do I need (LibreOffice/Poppler/LLM/mock), and what is the minimal runnable command?”

## Core Value (Context Engineering · Category-first RAG)

This project moves the key of RAG “retrieval + generation” upstream to a more fundamental principle: **deciding what information should enter the context window at each LLM step (Context Engineering)**. For enterprise PPTs (dense, loosely structured, noisy), the core value is:

- **Treat context as a scarce resource, not a “dumping ground”**: distill noisy, redundant raw content into dense knowledge units offline, reducing wasted tokens and attention fragmentation (context rot) for more consistent answers.
- **Fight retrieval fragmentation with “category-first” ingestion**: summarize per slide first, then aggregate by topic into `category_summary` so “key concepts scattered across slides” become ready-to-use context modules; at query time, retrieve category summaries first and only add a small number of evidence slides when needed.
- **Operationalize distillation with Map-Reduce for scale and cost control**: Map (local distillation) → Merge (semantic aggregation) → Reduce (final categories) turns a methodology into tunable parameters and reproducible artifacts (manifest/version/config).
- **Traceable and regression-friendly**: category summaries carry slide references (slide refs/citations) for review; with a golden question set + regression eval + monitoring logs, changes (granularity, merge strategy, Top-K, thresholds, prompts) become measurable in quality/cost/latency.

Typical scenarios:
- **Pre-sales / solution consultants**: answer frequent questions like “core capabilities / differentiators / target industries / implementation path / success cases” with traceable references.
- **Multi-project knowledge base**: standardize each project PPT into category summaries, enable project-level filtering, and deploy cheaply.
- **Delivery alignment**: use project profiles + category summaries to drive requirement clarification and internal alignment, reducing “message drift”.
- **Batch ingestion & governance**: offline distillation (with validation/fallback) reduces hallucinations and rework caused by unstable online retrieval quality.

---

## Badges (Optional)

![License](https://img.shields.io/badge/license-Private-blue)
![Build](https://img.shields.io/badge/build-passing-brightgreen)
![Status](https://img.shields.io/badge/status-active-success)

---

## Table of Contents

- [Solution Advisor · PPT Parsing & Project Profiling Pipeline](#solution-advisor--ppt-parsing--project-profiling-pipeline)
  - [AI-Assisted Quickstart (Claude / Codex)](#ai-assisted-quickstart-claude--codex)
  - [Core Value (Context Engineering · Category-first RAG)](#core-value-context-engineering--category-first-rag)
  - [Badges (Optional)](#badges-optional)
  - [Table of Contents](#table-of-contents)
  - [Features](#features)
  - [Architecture / Design Overview](#architecture--design-overview)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Usage Examples](#usage-examples)
    - [Main PPT Parsing Pipeline](#main-ppt-parsing-pipeline)
    - [Vector DB Management](#vector-db-management)
    - [QA CLI](#qa-cli)
    - [Streamlit Web UI (Recommended)](#streamlit-web-ui-recommended)
    - [Monitoring & Cache](#monitoring--cache)
    - [Outputs](#outputs)
  - [Project Layout](#project-layout)
  - [Development Guide](#development-guide)
  - [Testing](#testing)
  - [Deployment (If Applicable)](#deployment-if-applicable)
  - [Roadmap (Optional)](#roadmap-optional)
  - [Contributing](#contributing)
  - [License](#license)
  - [Maintainers / Contact](#maintainers--contact)
  - [Implementation Notes (Plain-English, Category-first RAG)](#implementation-notes-plain-english-category-first-rag)
    - [What problem are we solving?](#what-problem-are-we-solving)
    - [Why “category-first”?](#why-category-first)
    - [How does it work?](#how-does-it-work)

---

## Features

- End-to-end pipeline: PPT render → text extraction → per-slide summary → project profile → `rag_documents.json`. By default, RAG documents are generated via a **high-quality manual workflow** (see `docs/generate_rag_documents.md`) focused on `category_summary + overview`.
- Optional automated RAG: when `auto_ragprep_enabled` is enabled, use LangGraph Map-Reduce to generate `category_summary/overview` aligned with the manual aggregation conventions; the legacy per-slide QA auto-chain is deprecated.
- RAG shape: primary chunks are `category_summary` (topic aggregation) + `overview`; `qa_pair/metrics/topic/step` are compatibility add-ons controlled via toggles.
- Vector retrieval with guardrails: M3E embeddings + Chroma + a similarity threshold (`top_k/top_n/tau` tunable); return empty when no strong match is found.
- Multiple entry points: `python -m src` (pipeline), `qa_cli` (QA; supports guided mode), `vectordb_cli` (embedding ops), and **Streamlit Web UI** (project selection, citations, feedback, guided dialogue).
- Monitoring & cache: `QAMonitor` exact-match cache (default TTL 7 days; versioned invalidation) + JSONL logs; cache hits are printed as `[cache hit/<level>]`.
- Low-coupling config: LLM/embedding/vectordb/rendering tools are replaceable; supports `llm_provider=mock` for offline debugging.

---

## Architecture / Design Overview

- Core components:
  - `renderer/libreoffice.py`: PPTX → PDF → PNG (two-step rendering)
  - `extractor/ppt_extractor.py`: extract slide text and speaker notes
  - `summarizer/`: per-slide summaries + project profile (LLM; mock supported)
  - `rag/map_reduce_graph.py`: LangGraph Map-Reduce to auto-generate `category_summary + overview` (only when `auto_ragprep_enabled=true`)
  - `rag/chunk_generator.py`: QA pairs and multi-type chunks (compat mode; toggle-controlled)
  - `embeddings/m3e_model.py`: M3E embedding model wrapper (768 dims)
  - `vectordb/chroma_store.py`: Chroma store wrapper + retrieval guardrails
  - `qa/qa_engine.py`: retrieval + LLM generation + monitoring/cache; `qa/dialogue_orchestrator.py` provides guided dialogue
  - `pipeline.py`: end-to-end orchestration (refine + stage-level force rerun)
- Interfaces:
  - `python -m src`: main PPT parsing CLI
  - `src/scripts/qa_cli.py`: CLI QA (`--guided` enables guided multi-turn)
  - `src/scripts/vectordb_cli.py`: vector DB ops (import/batch import/query/stats/delete)
  - `src/ui/streamlit_app.py`: Streamlit Web UI
- Data & storage: local filesystem + `chroma_db/` + `logs/qa_sessions/` (logs & cache)
- Extension points: LLM client, RAG toggles (manual vs auto; chunk types), recall/rerank params, guided templates/prompts

See `docs/` for implementation plans/design notes and each module’s `AGENTS.md` / `CLAUDE.md`.

---

## Prerequisites

- Python 3.9+
- LibreOffice (provides the `soffice` executable)
- Poppler (provides `pdftoppm`)
- Optional: a real LLM API key (otherwise use `llm_provider: mock`)

---

## Installation

```bash
# Clone
git clone https://github.com/your-org/solution_advisor.git
cd solution_advisor

# Install dependencies
pip install -r requirements.txt

# For the Web UI, also install Streamlit
pip install streamlit>=1.30.0
```

Install LibreOffice / Poppler (required for PPT rendering):
- Windows: install LibreOffice and make sure `soffice.exe` is on PATH; install Poppler for Windows and add the directory containing `pdftoppm.exe` to PATH.
- macOS: `brew install --cask libreoffice`, `brew install poppler`
- Linux: `apt/yum install libreoffice`, `apt/yum install poppler-utils`

Verify:
```bash
soffice --headless --version
pdftoppm -h | head -n 1
```

If not on PATH, set absolute paths in `config/settings.yaml` (see “Configuration”).

---

## Configuration

- Copy the template: `config/settings.example.yaml -> config/settings.yaml` and adjust as needed.
- Key settings:
  - `llm_provider` / `llm_model` / `llm_api_key` / `llm_base_url`: LLM config (supports `mock`)
  - `vectordb_enabled` / `vectordb_provider` / `vectordb_persist_dir`: vector DB config
  - `embedding_model` / `embedding_device`: M3E model and device selection (cpu/cuda/mps)
  - `auto_ragprep_enabled`: default `false` for manual `rag_documents.json` generation (see `docs/generate_rag_documents.md`, focusing on `category_summary + overview`); set `true` to enable LangGraph Map-Reduce auto generation. Related params: `map_batch_size` / `map_max_categories_per_batch` / `reduce_target_categories` / `langgraph_max_concurrency` / `map_temperature` / `reduce_temperature`.
  - Chunk toggles: `enable_category_summary_chunks` (default true) controls aggregated chunks; `enable_llm_classify` / `enable_topic_chunks` / `enable_step_chunks` / `enable_metrics_chunks` are compatibility options.
  - Guided QA: `qa.guided.enabled` / `templates_path` / `gap_similarity_threshold` / `llm_prompt_path`
  - Monitoring & cache: `qa.cache.cache_ttl_days` / `cache_backend` / `vectordb_version` (global cache invalidation)
  - `soffice_path` / `pdftoppm_path`: rendering tool paths (optional; defaults to PATH)
- CLIs accept `--config` to specify a config file; `--no-vectordb` skips vector DB ingestion and only generates embedding files.

---

## Usage Examples

### Main PPT Parsing Pipeline

```bash
# Basic
python -m src --input ppts/ChatBI产品介绍_2025.pptx --output ppt_outputs/ChatBI产品介绍_2025

# Force rerun (ignore manifest)
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --force

# Rerun only rendering/extraction or summarization
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --force-capture
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --force-interpret

# Refine mode: rerun only low-confidence pages
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --refine --threshold 0.6 --pages "1,3,5"

# Skip vector DB ingestion; only generate embeddings files
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --no-vectordb
```

- Default outputs include `slides/`, `slide_texts.jsonl`, `page_summaries/`, and `doc_summary/project_profile.json`.
- **Default RAG path is the manual high-quality workflow**: generate `embeddings/rag_documents.json` (focused on `category_summary + overview`) following `docs/generate_rag_documents.md`, then rerun the pipeline (or use `vectordb_cli import-docs`) to ingest into the vector DB.
- Optional auto RAG: set `auto_ragprep_enabled: true` in `config/settings.yaml` to let the pipeline run LangGraph Map-Reduce and ingest automatically (useful for batch/draft generation).
- All outputs and errors are recorded in `manifest.json` and can be reused to avoid repeated work.

### Vector DB Management

```bash
# Import a single project
python -m src.scripts.vectordb_cli import-docs --input ppt_outputs/ChatBI/embeddings/rag_documents.json

# Batch import all projects (scan ppt_outputs/*/embeddings/rag_documents.json)
python -m src.scripts.vectordb_cli batch-import --input-dir ppt_outputs

# Query the vector DB
python -m src.scripts.vectordb_cli query --text "ChatBI的核心功能" --top-k 5

# Show stats
python -m src.scripts.vectordb_cli stats

# List projects
python -m src.scripts.vectordb_cli list-projects

# Delete a project
python -m src.scripts.vectordb_cli delete --project ChatBI
```

### QA CLI

```bash
# Basic QA
python -m src.scripts.qa_cli -q "ChatBI的核心功能是什么" --config config/settings.yaml

# Filter by project
python -m src.scripts.qa_cli -q "核心功能是什么" -p ChatBI --config config/settings.yaml

# Custom retrieval params
python -m src.scripts.qa_cli -q "架构设计" --top-k 8 --top-n 5 --tau 0.5

# Guided dialogue (clarification + follow-up suggestions)
python -m src.scripts.qa_cli -q "数据落地怎么部署" --guided
```

### Streamlit Web UI (Recommended)

```bash
# Start UI
streamlit run src/ui/streamlit_app.py

# Custom port
streamlit run src/ui/streamlit_app.py --server.port 8501
```

Features:
- Project selection + parameter tuning (`top_k`, `top_n`, `tau`)
- Natural-language answers (paragraph-style, not rigid bullet lists)
- Cache status indicator
- Conversation history management
- Feedback collection (upvote/downvote/comment)
- Optional: show citations (for debugging)
- Optional: guided dialogue mode (reuses `DialogueOrchestrator`)

URL: http://localhost:8501

### Monitoring & Cache

- `qa_cli` enables `QAMonitor` by default
- Cache hits are prefixed with `[cache hit/<level>]`
- Logs and exact-match cache are written to `logs/qa_sessions/` (daily JSONL)
- Semantic cache has been removed; caching depends only on exact matching (default TTL 7 days)
- `qa.cache.vectordb_version` can invalidate cache globally

### Outputs

- `slides/001.png`…: rendered slide images
- `slide_texts.jsonl`: extracted raw text per slide
- `page_summaries/001.json`…: per-slide summaries
- `doc_summary/project_profile.json`: aggregated project profile
- `embeddings/rag_documents.json`: RAG documents (default: `category_summary + overview`; compatibility: `qa_pair/metrics/...`)
- `manifest.json`: metadata and error records

---

## Project Layout

```bash
.
├─docs/                     # Requirements/design/plan docs
├─ppts/                     # Input PPT assets
├─ppt_outputs/              # Rendered & summarized outputs (build artifacts)
│  └─<project>/
│     ├─slides/             # PNG slide images
│     ├─slide_texts.jsonl   # Extracted raw text
│     ├─page_summaries/     # Per-slide summary JSON
│     ├─doc_summary/        # Project profile JSON
│     ├─embeddings/         # RAG docs (rag_documents.json)
│     └─manifest.json       # Metadata and error records
├─src/                      # Core code
│  ├─renderer/              # PPTX → PDF → PNG rendering
│  ├─extractor/             # Text and speaker notes extraction
│  ├─summarizer/            # Per-slide summary + project profile (LLM)
│  ├─prompts/               # Prompt management
│  ├─rag/                   # RAG generation: QA/multi-chunk + LangGraph Map-Reduce aggregation
│  ├─embeddings/            # M3E embedding wrapper
│  ├─vectordb/              # Chroma store + guardrails
│  ├─qa/                    # QA engine + monitoring/cache
│  ├─ui/                    # Streamlit Web UI
│  ├─scripts/               # CLI tools (qa_cli, vectordb_cli)
│  ├─pipeline.py            # Orchestration
│  ├─config.py              # Config loading
│  ├─models.py              # Pydantic models
│  └─__main__.py            # CLI entrypoint
├─tests/                    # Unit + end-to-end tests
├─config/                   # Config templates and defaults
│  ├─settings.example.yaml  # Template
│  └─settings.yaml          # Local config (gitignored)
├─chroma_db/                # Chroma persistence
├─logs/                     # Logs and cache
│  └─qa_sessions/           # QA JSONL logs + exact cache
├─snapshots/                # Manual screenshots/acceptance notes (optional)
└─venv/                     # Local virtualenv (optional)
```

---

## Development Guide

- Style: PEP8; `black`/`isort` recommended (not enforced)
- Commits: short Chinese description (e.g., “更新渲染异常处理”)
- Branching: keep `main`; use feature branches `feature/*`

---

## Testing

```bash
pytest tests/ -v

# Run specific test files
pytest tests/test_pipeline_e2e.py -v
pytest tests/test_dialogue_orchestrator.py -v   # Guided dialogue logic

# With coverage
pytest tests/ --cov=src --cov-report=html
```

> If LibreOffice/Poppler is missing or LLM is not configured, relevant tests are skipped automatically. Use `llm_provider: mock` for offline runs.  
> Embedding regression: `tests/tmp_run_tests.py` generates `tests/tmp_embedding_test_round1.json` for comparison. `src/scripts/qa_eval_llm.py` can run LLM self-eval on `tests/qa_test_results/qa_test_*.json`.

---

## Deployment (If Applicable)

- Target: local / self-hosted server
- Delivery: Python CLI; can be containerized (add your own Dockerfile)
- Key config: LLM/vector DB/rendering tool paths in `config/settings.yaml`
- Dependencies: LibreOffice, Poppler, LLM API (or mock), Chroma vector DB

---

## Roadmap (Optional)

- [ ] Improve Dockerization and one-click install scripts
- [ ] RAG v2: automated embedding quality baselines and regression tests
- [ ] Multi-model strategy and automatic rerank parameter tuning
- [ ] Add task queue and batch processing
- [ ] Expand edge-case PPT samples; improve fallback/alerts

---

## Contributing

- Before submitting a PR, ensure all tests pass and relevant docs are updated
- For feature requests/issues, open an issue or coordinate via internal channels
- Code reviews are handled by the core maintainers on rotation

---

## License

This project is currently for internal use only. License: Private (not public). Contact maintainers before any external distribution.

---

## Maintainers / Contact

- Owner: Solution Advisor team (internal)
- Contact: WeCom / email (see internal directory)

---

## Implementation Notes (Plain-English, Category-first RAG)

### What problem are we solving?

Project-introduction PPTs are dense, loosely structured, and stylistically inconsistent. Feeding the whole deck to an LLM either exceeds context limits or produces fragmented, non-traceable answers. The goal is to distill PPT knowledge into retrievable, traceable RAG assets that reliably answer high-frequency questions (e.g., “What are the core capabilities?”) and support multi-project, low-cost internal deployment.

### Why “category-first”?

1) **Traceable and anti-fragmentation**: summarize per slide, then aggregate by topic into `category_summary`, each carrying slide refs. Compared with per-slide QA, category aggregation reduces duplication and noise.  
2) **Controllable context**: category count is stable (~6–12) and text length is predictable, yielding a cleaner vector store and less reranking over near-duplicate QA.  
3) **Manual + automated dual track**: manual path guarantees quality (default); for batch, enable LangGraph Map-Reduce to draft outputs and then spot-check to balance cost/efficiency.  
4) **Compatible with legacy strategies**: keep multi-chunk toggles for regression or special cases without breaking existing data.

### How does it work?

1) **Decompose into a verifiable chain**: render → extract text → per-slide summary → project profile. Each step writes a manifest for reruns and debugging.  
2) **Category aggregation (manual default)**: read `page_summaries/*.json` and aggregate similar slides into `category_summary` (summary + 3–5 QA + source citations) plus a project-level `overview`; write to `embeddings/rag_documents.json`.  
3) **Auto Map-Reduce (optional, LangGraph)**: when `auto_ragprep_enabled=true`, run parallel Map-Reduce and produce the same artifact format (`category_summary + overview`):
   - **Batching**: split `page_summaries` by `map_batch_size` (default 10 slides) to control context size.  
   - **Map**: each batch yields 3–6 “local categories”, each with a 100–150 word summary, optional 1–2 QA, and `source_slide_refs`; temperature `map_temperature` (default 0.2).  
   - **Merge**: collect all local categories and merge by name/semantics; high-similarity ones are merged; total category count is constrained by `reduce_target_categories` (default 10).  
   - **Reduce**: for each merged global category, generate a 200–300 word `category_summary` + 3–5 QA; dedupe/sort citations; temperature `reduce_temperature` (default 0.2).  
   - **Overview**: generate a 150–200 word project-level overview from all category summaries.  
   - **Concurrency & fallback**: Map/Reduce nodes are controlled by `langgraph_max_concurrency`; failures fall back to heuristic summaries and are recorded in the manifest.  
   - **Output validation**: validate structure/length/citations, then write `embeddings/rag_documents.json`; failures are written to `manifest.errors`.  
4) **Embedding + guardrails**: batch encode with `moka-ai/m3e-base` (auto CPU/CUDA/MPS). Metadata includes project/slide/level/chunk_type/category_id/confidence. Return empty when similarity is low to reduce hallucinations.  
5) **Retrieval + answering**: `ChromaStore.query_with_guardrails(..., tau=0.5, top_k=8, top_n=5)` with project filtering and optional detail-slide boosting; `QAEngine` provides a unified wrapper shared by CLI/UI.  
6) **Monitoring + cache**: `QAMonitor` writes exact-match cache and logs (TTL 7 days; `vectordb_version` invalidates globally). Cache hits are printed as `[cache hit/<level>]` to support rollout and traceability.

