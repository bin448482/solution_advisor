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

### Vector Database Management

```bash
# Import single project
python -m src.scripts.vectordb_cli import \
    --input ppt_outputs/ChatBI/embeddings/rag_documents.json

# Batch import all projects
python -m src.scripts.vectordb_cli batch-import --input-dir ppt_outputs

# Query vector database
python -m src.scripts.vectordb_cli query --text "ChatBI的核心功能" --top-k 5

# Show statistics
python -m src.scripts.vectordb_cli stats

# Delete project
python -m src.scripts.vectordb_cli delete --project ChatBI
```

### Retrieval Defaults & Guardrails（生产/测试共用）

- 包装函数：`ChromaStore.query_with_guardrails(text, project_name=None, where=None, top_k=8, top_n=5, tau=0.5)`（src/vectordb/chroma_store.py）。
- 项目过滤：若未传 where，单项目场景自动过滤；多项目可传 `project_name` 或自定义 `where`。
- 召回与重排：`top_k=8` 召回 → 相似度 + 细节页/slide 加分 → 取前 5。
- 阈值护栏：Top-1 相似度 `< 0.5` 返回空列表（由上层决定“未找到相关内容”的文案）。
- page_type 归一：查询阶段将 page_type 归一到 data_sources/deployment/api/performance/tech_stack/architecture，再用于加分与展示。
- 测试脚本：`tests/tmp_run_tests.py` 直接调用该包装函数，输出 `tests/tmp_embedding_test_round1.json`。

### Running the QA CLI (RAG问答)

```bash
python -m src.scripts.qa_cli -q ChatBI的核心功能是什么 -p ChatBI --config config/settings.yaml --top-k 8 --top-n 5 --tau 0.5
```
- CLI 默认启用 `QAMonitor`：命中缓存会在答案前打印 `[cache hit/<level>]`，日志与精确缓存写 `logs/qa_sessions/qa_logs_YYYYMMDD.jsonl` / `qa_cache.jsonl`；语义缓存已下线，命中仅依赖精确缓存（TTL=7d，可用 `qa.cache.vectordb_version` 统一失效）。

- 输入：问题必填；可选 project 过滤。
- 输出：answer + sources + status（success/no_context/error）。
- 依赖：已导入的 Chroma 向量库（ppt_outputs/*/embeddings/rag_documents.json），共享 Settings/LLMClient。

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
[RAGPreparer] Clean summaries + prepare embeddings → embeddings/rag_documents.json
  ├─ clean_summary_for_embedding: Unnest JSON, strip <think> blocks, flag noise
  ├─ prepare_slide_embedding: Convert each PageSummary to embedding doc
  └─ prepare_project_embedding: Convert ProjectProfile to overview doc
  ↓
[VectorDB] (Optional) Insert documents into Chroma with M3E embeddings
  ├─ M3EEmbedding: Generate 768-dim vectors for semantic search
  ├─ ChromaStore: Batch insert with metadata (project, slide_no, confidence, level)
  └─ Idempotent upsert: Safe to re-run without duplicates
  ↓
[Pipeline] Write manifest.json with metadata, errors, rag_documents, and vectordb_metrics
```

### Key Architectural Decisions

**Rendering Strategy**: Two-step conversion (PPTX → PDF → PNG) via LibreOffice headless provides better reliability than direct conversion. The intermediate PDF is kept for debugging.

**Text Enhancement**: Combines visual analysis (LLM Vision API on slide images) with extracted text (titles, content, speaker notes) to reduce hallucination and improve accuracy.

**Error Handling Philosophy**:
- Critical errors (missing dependencies, invalid config) → fail fast
- Single-page errors → continue processing, collect errors in manifest
- LLM API errors → retry 3x with exponential backoff
- RAG preparation errors → flag in manifest with stage markers:
  - `rag_clean`: Noise/JSON issues in summaries (bullets_look_like_json, detail_unpack_failed)
  - `rag_prep`: General RAG preparation failures

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
├── rag.py                 # RAG document preparation (pipeline.py:90-113)
│   ├── prepare_slide_embedding()    # PageSummary → embedding doc
│   ├── prepare_project_embedding()  # ProjectProfile → overview doc
│   └── clean_summary_for_embedding() # Noise detection & JSON unnesting
├── renderer/
│   ├── base.py           # Abstract Renderer interface
│   └── libreoffice.py    # LibreOffice implementation
├── extractor/
│   └── ppt_extractor.py  # python-pptx text extraction
├── summarizer/
│   ├── llm_client.py     # LLM API wrapper (OpenAI-compatible)
│   ├── page_summarizer.py    # Single page → PageSummary
│   └── profile_generator.py  # All summaries → ProjectProfile
├── qa/                   # QAEngine: vector检索 + 提示构建
│   └── qa_engine.py      # answer(question) → answer/sources/status
├── embeddings/           # M3E embedding model integration
│   └── m3e_model.py      # Chinese text embedding with auto-download & caching
├── vectordb/             # Chroma vector database integration
│   └── chroma_store.py   # Document insertion, querying, management
├── scripts/              # Standalone CLI tools
│   ├── vectordb_cli.py   # Vector DB management commands
│   └── qa_cli.py         # Q&A CLI (vector retrieval + LLM)
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
│   └── rag_documents.json    # Slide-level + project-level docs for vector DB
└── manifest.json
```

**manifest.json** contains: input file hash, timestamp, page count, processing duration, error list (slide_no, stage, error message), and `rag_documents` count.

**Error stages** in manifest:
- `render`: Slide rendering failures
- `extract`: Text extraction issues
- `summarize`: Page summarization errors
- `profile`: Profile generation failures
- `rag_clean`: Noise/JSON issues in summaries (bullets_look_like_json, detail_unpack_failed)
- `rag_prep`: General RAG preparation failures
- `vectordb`: Vector database insertion failures

**manifest.json** also includes `vectordb_metrics` when vector DB is enabled:
- `documents_inserted`: Number of successfully inserted documents
- `documents_failed`: Number of failed insertions
- `embedding_time_seconds`: Time spent generating embeddings
- `insertion_time_seconds`: Time spent inserting into Chroma
- `collection_name`: Target collection name

**embeddings/rag_documents.json** structure:
- Array of embedding-ready documents
- Each document contains: `id`, `text` (semantic content), `metadata` (project_name, slide_no, page_type, confidence, level), `original_json`
- Two levels: slide-level (detail) and project-level (overview)

## Configuration

Configuration now comes from YAML (no .env):
```
config/settings.yaml  # gitignored real config
config/settings.example.yaml  # template with placeholders
```
CLI flag `--config` overrides the path; otherwise defaults to `config/settings.yaml`.

**Mock Provider for Testing**: For offline testing or when LLM API is unavailable, set `llm_provider: mock` in settings.yaml. 模式下 QA 生成走内置伪造问答（不依赖外部 LLM），保证 RAG 产物完整且可用于冒烟。

**RAG Feature Toggles（成本/回滚控制）**：
- `enable_llm_classify`：是否调用 LLM 分类 QA 对（默认 false）
- `enable_topic_chunks` / `enable_step_chunks` / `enable_metrics_chunks`：是否生成对应 chunk（默认 false）

### Vector Database Configuration

**Enable Vector DB Integration**:
```yaml
vectordb_enabled: true                   # Enable automatic insertion into vector DB
vectordb_provider: chroma                # Vector database provider
vectordb_persist_dir: ./chroma_db        # Local persistence directory
vectordb_collection_name: project_slides # Collection name
```

**Embedding Model Configuration**:
```yaml
embedding_model: moka-ai/m3e-base        # HuggingFace model ID (m3e-base or m3e-large)
embedding_device: cpu                    # Device: cpu | cuda | mps (Apple Silicon)
embedding_batch_size: 32                 # Batch size for embedding generation
embedding_cache_dir: ./models            # Model cache directory
```

**Model Options**:
- `moka-ai/m3e-base`: 768-dim, ~400MB, balanced performance (recommended)
- `moka-ai/m3e-large`: 1024-dim, ~1.2GB, higher accuracy

**Device Selection**:
- `cpu`: Universal, slower (~2-5s per batch)
- `cuda`: NVIDIA GPU, 10-20x faster
- `mps`: Apple Silicon GPU, 5-10x faster

**Note**: First run downloads the model (~400MB for m3e-base) and caches it locally.

## Data Models (Pydantic)

**PageSummary** fields:
- `slide_no`, `title`, `one_liner` (≤30 chars)
- `bullets` (3-7 items), `details` (1-2 paragraphs)
- `image_caption` (optional, for visual grounding from LLM vision)
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

**Manifest** fields:
- `input_file`, `file_hash`, `timestamp`, `output_dir`
- `page_count`, `duration_seconds`
- `provider`, `model` (LLM configuration used)
- `page_summaries` (count of successfully generated summaries)
- `rag_documents` (count of documents in embeddings/rag_documents.json)
- `vectordb_metrics` (optional, when vectordb_enabled=true): insertion statistics
- `errors` (list of dicts with stage, slide_no, error message)

**VectorDBMetrics** fields (when vector DB enabled):
- `documents_inserted`: Number of successfully inserted documents
- `documents_failed`: Number of failed insertions
- `embedding_time_seconds`: Time spent generating embeddings
- `insertion_time_seconds`: Time spent inserting into Chroma
- `collection_name`: Target collection name

## RAG Document Generation

### RAG v2 (QA-Pair Approach) - Current Implementation

The pipeline now uses a QA-pair-centric approach (src/rag/ package) that generates multiple chunk types per slide for enhanced retrieval quality.

**Architecture**:
```
PageSummary → [QAGenerator] → 5-10 QA pairs
                    ↓
            [LLMClassifier] → Batch classify (8 categories)
                    ↓
            [ChunkGenerator] → Multiple chunk types:
                    ├─ qa_pair (5-10 per slide)
                    ├─ topic (1-3 if applicable)
                    ├─ step (1-5 if applicable)
                    ├─ metrics (0-2 if applicable)
                    └─ overview (1 per project)
```

**Key Features**:
- **QA Pairs**: Natural question-answer pairs with alternative phrasings
- **LLM Classification**: 8 categories (positioning, features, architecture, deployment, integration, cases, comparison, roadmap)
- **Batch Processing**: 8-10 QA pairs classified per LLM call (80% cost reduction)
- **Multi-Chunk Strategy**: Different chunk types for different query patterns
- **Enhanced Metadata**: chunk_type, qa_question, alt_questions, answer, category_id, category_name

**Chunk Types**:
1. **qa_pair** (primary): Question + answer + alt_questions + keywords
2. **topic** (optional): Thematic content blocks for long-form answers
3. **step** (optional): Sequential/process steps
4. **metrics** (optional): Performance/data metrics
5. **overview** (project-level): Aggregated project summary

**Token Cost**: ~2050 tokens per slide (QA generation: 1800, classification: 250)

**See**: `src/rag/CLAUDE.md` for detailed documentation

### RAG v1 (Legacy) - Deprecated

The original single-chunk-per-slide approach is preserved in `src/rag/legacy.py` for reference.

**Two-Level Approach** (legacy):

**Slide-Level Documents** (detail):
- One document per PageSummary
- ID format: `{project_name}_slide_{slide_no:03d}`
- Semantic text includes: project name, page title, visual description, core summary, key points, details, keywords
- Metadata: project_name, slide_no, page_type (signals), entities, confidence, level="slide"
- Preserves original_json for full traceability

**Project-Level Document** (overview):
- Single aggregated document per ProjectProfile
- ID format: `{project_name}_overview`
- Semantic text includes: positioning, core value, target users, capabilities, differentiators, architecture, deployment, integrations, cases, risks, open questions
- Metadata: project_name, slide_no=0 (virtual), page_type=["overview", "profile"], level="project"
- Enables high-level project discovery queries

### Noise Handling & Cleaning

The `clean_summary_for_embedding()` function addresses LLM output quality issues:

**JSON Unnesting**:
- Detects JSON-like content in `details` field (starts with `{` or `[`)
- Attempts to parse and extract nested `bullets` and `details` fields
- Flags `detail_unpack_failed` if parsing fails

**Think Block Removal**:
- Strips `<think>...</think>` blocks that some models prepend
- Ensures clean semantic text for embedding

**Bullet Cleaning**:
- Detects bullets containing embedded JSON
- Attempts to extract and flatten nested bullet arrays
- Flags `bullets_look_like_json` if suspicious content remains

**Error Flagging**:
- Issues are recorded in manifest.json with stage=`rag_clean`
- Includes slide_no and specific error type for manual review
- Processing continues with cleaned data

### Output Format

**embeddings/rag_documents.json** structure:
```json
[
  {
    "id": "ChatBI_slide_001",
    "text": "项目: ChatBI\n页面标题: ...\n核心总结: ...\n关键点:\n- ...\n详情: ...\n关键词: ...",
    "metadata": {
      "project_name": "ChatBI",
      "source": "ChatBI",
      "slide_no": 1,
      "page_type": ["positioning", "features"],
      "entities": ["ChatBI", "BI", "数据分析"],
      "confidence": 0.9,
      "level": "slide"
    },
    "original_json": "{...}"
  },
  {
    "id": "ChatBI_overview",
    "text": "项目综述: ChatBI\n定位: ...\n核心价值: ...\n目标用户: ...",
    "metadata": {
      "project_name": "ChatBI",
      "source": "ChatBI",
      "slide_no": 0,
      "page_type": ["overview", "profile"],
      "level": "project"
    },
    "original_json": "{...}"
  }
]
```

### Integration

RAG preparation runs automatically after profile generation:
1. Pipeline generates all PageSummary objects (parallel)
2. Pipeline generates ProjectProfile (sequential)
3. RAG step processes each summary through `clean_summary_for_embedding()`
4. RAG step calls `prepare_slide_embedding()` for each cleaned summary
5. RAG step calls `prepare_project_embedding()` for the profile
6. All documents written to embeddings/rag_documents.json
7. Document count recorded in manifest.json as `rag_documents`
8. Any cleaning issues flagged in manifest.errors with stage=`rag_clean`

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
- Docs (docs/): `<领域/产品>_<主题>_<类型>.md`（类型推荐：需求分析/实施计划/测试方案/复盘），中文命名，首字母大写，无空格；示例：`PPT解析与项目画像_增量修复方案.md`。

**Generated Artifacts**: `ppt_outputs/` is treated as build artifacts. Update `.gitignore` if these should not be committed.

## Documentation Structure & Maintenance

The repository uses paired hierarchical docs (`AGENTS.md` + `CLAUDE.md`) to keep per-module guidance close to the code.

- **层级职责**：根目录文件承担全局规范与索引；子目录文件聚焦本模块的角色、入口、依赖与测试要点。
- **同步要求**：完成或调整模块功能后，务必更新该目录下的 `AGENTS.md` 与 `CLAUDE.md`（若为全局变更，同时更新根目录文件）。
- **新增模块**：新建目录时创建对应的 `AGENTS.md`/`CLAUDE.md`，并在根目录文件的索引表中补充引用说明。

### @AGENTS.md 索引
| 路径 | 职责概述 |
| --- | --- |
| `AGENTS.md` | 全局开发规范、目录职责索引、常用命令。 |
| `src/AGENTS.md` | PPT 解析主流程概览、配置与依赖。 |
| `src/renderer/AGENTS.md` | PPTX → PDF/PNG 渲染策略与外部工具要求。 |
| `src/extractor/AGENTS.md` | 幻灯片文本抽取流程与对齐假设。 |
| `src/summarizer/AGENTS.md` | LLM 总结/画像生成链路与客户端配置。 |
| `src/embeddings/AGENTS.md` | M3E 向量模型加载与编码策略。 |
| `src/vectordb/AGENTS.md` | Chroma 存储封装、检索护栏与项目过滤。 |
| `src/qa/AGENTS.md` | QA 引擎 + 监控/缓存职责、配置键说明。 |
| `src/scripts/AGENTS.md` | QA/Vectordb CLI 参数、输出与错误处理。 |
| `tests/AGENTS.md` | 测试覆盖、跳过条件与烟囱测试说明。 |

### @CLAUDE.md 索引
| 路径 | 职责概述 |
| --- | --- |
| `CLAUDE.md` | 高层概览、架构与端到端用法。 |
| `src/CLAUDE.md` | 核心管线详细说明、文件/数据流与配置示例。 |
| `src/renderer/CLAUDE.md` | 渲染模块设计、两步转换策略及依赖。 |
| `src/extractor/CLAUDE.md` | 文本抽取设计、数据模型与边界情况。 |
| `src/summarizer/CLAUDE.md` | 单页总结/画像提示词、LLM 客户端及错误处理。 |
| `src/embeddings/CLAUDE.md` | 向量模型选择、缓存、设备策略与性能提示。 |
| `src/vectordb/CLAUDE.md` | Chroma 集成、检索护栏与统计/维护命令。 |
| `src/qa/CLAUDE.md` | QA Engine 提示构建、输出格式与 guardrail 逻辑。 |
| `src/scripts/CLAUDE.md` | CLI 使用案例、参数说明与常见故障排查。 |

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
