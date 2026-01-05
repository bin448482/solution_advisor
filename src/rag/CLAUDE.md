# RAG Package (src/rag/) - Claude Code Guide

## Overview

RAG 模块现支持两条路径：

1) **默认（人工）**：关闭 `auto_ragprep_enabled`，人工生成 `embeddings/rag_documents.json`。  
2) **自动（LangGraph Map-Reduce，2026-01-05 新增）**：开启 `auto_ragprep_enabled` 时，使用 `map_reduce_graph.py` 生成 **仅** `category_summary` + `overview`，专注聚合质量与可追溯性；旧的 QA/分类/多 chunk 自动分支已被替换。

## Architecture

### Data Flow

**自动模式（LangGraph）**
```
PageSummary list
    ↓ prepare_batches (map_batch_size)
map_categories (并行，3-6 类/批，JSON 严格输出)
    ↓ merge_categories (按名称/语义合并，目标 6-12 类；可压缩“其他信息”)
reduce_categories (并行，200-300 字摘要 + 3-5 QA，引用 slide_no)
    ↓ build_overview (150-200 字项目综述)
validate_emit → embeddings/rag_documents.json （category_summary + overview）
```

**Legacy/辅助模块（仍保留供人工或扩展）**
```
QAGenerator → LLMClassifier → ChunkGenerator (qa/topic/step/metrics/category_summary/overview)
```

## Data Models (models.py)

### Category Enum

8 standard categories for content classification:

```python
class Category(str, Enum):
    POSITIONING = "positioning"      # 产品定位、核心价值
    FEATURES = "features"            # 功能特性、能力
    ARCHITECTURE = "architecture"    # 技术架构、系统设计
    DEPLOYMENT = "deployment"        # 部署方式、交付模式
    INTEGRATION = "integration"      # 集成对接、API
    CASES = "cases"                  # 客户案例、POC
    COMPARISON = "comparison"        # 竞品对比、差异化
    ROADMAP = "roadmap"             # 产品规划、未来方向
```

### QAPair Model

```python
class QAPair(BaseModel):
    question: str                    # 5-200 chars
    answer: str                      # 10+ chars
    alt_questions: List[str]         # 0-3 alternative phrasings
    category: Category               # Enum value
    confidence: float                # 0.0-1.0
    source_slide: int                # Source slide number
    keywords: List[str]              # 3-8 keywords
```

### ChunkDocument Model

```python
class ChunkDocument(BaseModel):
    id: str                          # Unique ID (e.g., "ChatBI_slide_003_qa_001")
    text: str                        # Semantic text for embedding
    metadata: Dict[str, Any]         # Enhanced metadata
    original_json: Optional[str]     # Original data as JSON string
```

### ChunkMetadata Schema

```python
{
    "project_name": "ChatBI",
    "slide_no": 3,
    "chunk_type": "qa_pair",         # qa_pair|metrics|overview|category_summary|topic|step
    "level": "slide",                # slide|project|category
    "summary": null,                 # LangGraph reduce/overview 会写入
    "qa_examples": null,             # LangGraph reduce QA 列表
    "confidence": 0.92,

    # QA-specific fields
    "qa_question": "ChatBI支持哪些数据源?",
    "alt_questions": ["ChatBI能连接什么数据库", "支持的数据源类型"],
    "answer": "ChatBI支持MySQL、PostgreSQL...",

    # Classification
    "category_id": "integration",
    "category_name": "集成对接",

    # Legacy fields (for compatibility)
    "page_type": ["data_sources", "integration"],
    "entities": ["ChatBI", "MySQL", "PostgreSQL"],
    "source_slide_refs": [3],
    "source_file": "page_summaries/003.json",
    "source_files": null
}
```

## LangGraph Map-Reduce (map_reduce_graph.py)

### 作用
- 自动模式唯一入口：`MapReduceCategoryGraph.run(summaries)` → 写 `embeddings/rag_documents.json`
- 产物：`category_summary`（每类 1 条，含 summary/qa_examples/source_slide_refs/source_files）+ `overview`（1 条）。

### 配置（Settings）
- `map_batch_size` (默认 10) — Map 批大小（页数）
- `map_max_categories_per_batch` (默认 6) — 每批最多类别
- `reduce_target_categories` (默认 10) — 合并后类别上限，超出会收敛为“其他信息”
- `langgraph_max_concurrency` (默认 4) — Map/Reduce 并发线程
- `map_temperature` / `reduce_temperature` — 节点温度
- 开关：`auto_ragprep_enabled=true` 才会走该流

### 节点
- `prepare_batches`：按批拆分 summaries
- `map_categories`：并行调用 LLM（mock 时生成确定性占位）；解析失败降级为启发式摘要
- `merge_categories`：同名/相似合并，数量超限时聚合到“其他信息”
- `reduce_categories`：并行生成 200-300 字摘要 + 3-5 QA（含 `source_slide_refs`）
- `build_overview`：150-200 字综述，基于所有类别摘要
- `validate_emit`：结构校验并落盘

### 回退与健壮性
- 解析失败 → 启发式 fallback；mock provider → 固定可预测输出
- 所有步骤错误收集到 `errors`，写入 `PipelineContext.errors`

### 输出特点
- `ChunkMetadata.summary` / `qa_examples` 写入，便于检索与 UI 展示
- 仅生成聚合类 chunk，避免碎片化；需要 QA 粒度时仍可人工/扩展使用 `QAGenerator + ChunkGenerator`

## QA Generator (qa_generator.py)

### Purpose

Generate 5-10 question-answer pairs from each PageSummary using LLM.

### Prompt Template

Chinese prompt that instructs the LLM to:
- Generate 5-10 QA pairs covering core information
- Questions should be natural (10-50 chars)
- Answers should be complete and standalone (50-300 chars)
- Provide 0-3 alternative phrasings per question
- Extract 3-8 keywords
- Assign confidence score (0.0-1.0)

### Key Features

- **Retry Logic**: 3 attempts with exponential backoff (1s, 2s, 4s)
- **Confidence Filtering**: Filters out QA pairs with confidence < 0.3
- **Error Handling**: Graceful degradation on parse failures
- **Category Inference**: Simple keyword-based category assignment (overridden by classifier)

### Token Usage

- Input: ~600 tokens (prompt + PageSummary)
- Output: ~1200 tokens (5-10 QA pairs)
- Total: ~1800 tokens per slide

## Batch Classifier (classifier.py)

### Purpose

Classify QA pairs into 8 categories using batch processing for cost efficiency.

### Batch Processing

- **Batch Size**: 8-10 QA pairs per LLM call
- **Cost Reduction**: 80% vs individual classification
- **Fallback**: On failure, keeps existing categories from QA generator

### Prompt Template

Chinese prompt that:
- Defines 8 categories with descriptions
- Lists QA pairs with index numbers
- Requests JSON output with category + reasoning

### Token Usage

- Input: ~200 tokens (prompt + batch of 8 QA pairs)
- Output: ~50 tokens (classifications)
- Total: ~250 tokens per slide (batch of 8)

## Chunk Generator (chunk_generator.py)

### Chunk Types

#### 1. QA Pair Chunks (Primary)

- **ID Format**: `{project}_slide_{slide_no:03d}_qa_{idx:03d}`
- **Text**: Question + alt_questions + answer + keywords
- **Metadata**: Full QA metadata with category
- **Count**: 5-10 per slide

#### 2. Topic Chunks (Optional)

- **Condition**: Slide has ≥3 bullets and substantial details (>50 chars)
- **ID Format**: `{project}_slide_{slide_no:03d}_topic_001`
- **Text**: Title + one_liner + bullets + details
- **Count**: 0-3 per slide

#### 3. Step Chunks (Optional)

- **Condition**: Sequential content detected (keywords: 步骤, 流程, 阶段, step, phase)
- **ID Format**: `{project}_slide_{slide_no:03d}_step_{idx:03d}`
- **Text**: Process title + step description
- **Count**: 0-5 per slide

#### 4. Metrics Chunks (Optional)

- **Condition**: Performance/data metrics detected (keywords: 性能, 指标, qps, tps, %)
- **ID Format**: `{project}_slide_{slide_no:03d}_metrics_001`
- **Text**: Metrics title + data points + explanation
- **Count**: 0-2 per slide

#### 5. Overview Chunk (Project-Level)

- **ID Format**: `{project}_overview`
- **Text**: Project positioning + core value + capabilities + architecture
- **Count**: 1 per project

### Decision Logic

```python
def decide_chunk_types(summary: PageSummary) -> List[str]:
    types = ["qa_pair"]  # Always generate QA pairs

    if _has_clear_topics(summary):
        types.append("topic")

    if _has_sequential_content(summary):
        types.append("step")

    if _has_metrics(summary):
        types.append("metrics")

    return types
```

## Pipeline Integration (pipeline.py)

### RAGPrepStage
- 默认：如果 `embeddings/rag_documents.json` 已存在且未强制，则复用。
- `auto_ragprep_enabled=false`：提示人工生成，返回 notes=manual_ragprep_required。
- `auto_ragprep_enabled=true`：调用 `MapReduceCategoryGraph`，产出 category_summary + overview；旧的 QA/classify/chunk 自动分支已移除。

### refine 流程
- 同样使用 Map-Reduce 自动模式（若开启开关）；否则复用已有 rag_documents 或提示人工。

### Error Handling

- QA generation failures: Recorded in manifest.errors (stage=qa_generation)
- Classification failures: Keeps existing categories
- Chunk generation: Continues with remaining chunks

## Vector DB Integration

### Enhanced Retrieval (chroma_store.py)

New method: `query_with_qa_ranking()`

**Features**:
- Retrieves 2×n_results candidates for reranking
- Boosts QA chunks (1.2x score multiplier)
- Boosts matching categories (1.3x multiplier)
- Boosts high confidence (0.8-1.2x multiplier)
- Applies similarity threshold (tau=0.5)

**Usage**:
```python
results = store.query_with_qa_ranking(
    query_text="ChatBI的核心功能",
    project_name="ChatBI",
    n_results=5,
    category_filter=["features", "positioning"],
    prefer_qa_chunks=True,
    tau=0.5
)
```

## Cost Analysis

### Per Slide

- QA Generation: 1800 tokens
- Classification (batch): 250 tokens
- **Total**: ~2050 tokens per slide

### Pricing (GPT-4o: $2.50/$10.00 per 1M tokens)

- Per slide: $0.0145
- Per PPT (30 slides): $0.44
- Batch (100 PPTs): $44

### Optimization

- Use GPT-4o-mini for classification: 90% cost reduction
- Cache QA pairs for unchanged slides (hash-based)
- Optimized per slide: $0.013

## Testing

### Unit Tests

```bash
pytest tests/test_qa_generator.py -v
pytest tests/test_classifier.py -v
pytest tests/test_chunk_generator.py -v
```

### Integration Test

```bash
# Run pipeline with mock LLM
python -m src --input ppts/demo.pptx --output ppt_outputs/demo --force

# Verify chunk types
cat ppt_outputs/demo/embeddings/rag_documents.json | jq '.[] | .metadata.chunk_type' | sort | uniq -c
```

### Expected Output

- 自动模式：`category_summary` × (6-12) + `overview` × 1
- 元数据包含 `source_slide_refs`/`source_files`/`summary`/`qa_examples`；写入 Chroma 前保持 list 结构（Chroma 插入层会处理 JSON 化）。

## Migration from Legacy

### Breaking Changes

- **Chunk Structure**: Multiple chunks per slide instead of one
- **Metadata Schema**: New fields (chunk_type, qa_question, alt_questions, answer, category_id, category_name)
- **ID Format**: New suffixes (_qa_001, _topic_001, etc.)

### Backward Compatibility

- Legacy functions preserved in `legacy.py`
- Old metadata fields (page_type, entities) still included
- Vector DB can handle both old and new formats

### Migration Steps

1. 备份现有 rag_documents.json
2. 如需自动模式：开启 `auto_ragprep_enabled=true`，运行 pipeline；如需粒度 QA，请继续用人工/legacy 生成
3. 重新写入向量库（若启用）
4. 校验类别摘要数量（6-12）与引用合法性

## Common Issues

### "No QA pairs passed confidence threshold"

**Cause**: All generated QA pairs have confidence < 0.3
**Solution**: Lower min_confidence or improve PageSummary quality

### "Classification failed"

**Cause**: LLM API error or invalid response format
**Solution**: Keeps existing categories from QA generator (fallback)

### "Chunk generation skipped"

**Cause**: Decision logic determined chunk type not applicable
**Solution**: Normal behavior - not all slides need all chunk types

## Future Enhancements

- Caching for QA pairs (hash-based)
- Fine-tuned classification model (reduce cost)
- Hierarchical chunking (parent-child relationships)
- Multi-language support
- Quality metrics (automatic evaluation)
