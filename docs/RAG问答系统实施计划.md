# Q&A System Implementation Plan

## Overview

实现一个基于向量检索和LLM的问答系统，用户输入问题后，系统通过Chroma向量数据库检索相关文档，然后使用LLM根据检索到的上下文生成答案。

## Architecture

```
User Question
    ↓
[QAEngine.answer()]
    ↓
[ChromaStore.query_with_guardrails()] → Retrieve top-N relevant documents
    ↓
[Build Prompt] → Question + Retrieved Context
    ↓
[LLMClient.generate()] → Generate Answer
    ↓
Return: {answer, sources, status}
```

## Implementation Steps

### 1. Create QA Engine Module

**File**: `src/qa/qa_engine.py`

**Core Class**: `QAEngine`
- `__init__(store: ChromaStore, llm_client: LLMClient)`
- `answer(question, project_name=None, top_k=8, top_n=5, tau=0.5) -> Dict`

**Logic Flow**:
1. Call `store.query_with_guardrails()` to retrieve relevant documents
2. If no results (below threshold), return "未找到相关内容" with status="no_context"
3. Build prompt with question + retrieved context
4. Call `llm.generate()` to get answer
5. Extract sources from results (project, slide_no, similarity)
6. Return structured output: {answer, sources, status}

**Prompt Template**:
```
你是一个专业的解决方案顾问助手。请基于以下检索到的文档内容回答用户问题。

要求:
1. 仅基于提供的文档内容回答，不要编造信息
2. 如果文档中没有相关信息，明确说明"文档中未提及"
3. 回答要准确、简洁、专业
4. 在回答中自然引用来源（如"根据第X页..."）

检索到的文档:
[文档1] 项目: {project}, 页码: {slide_no}
{document_text}

[文档2] ...

用户问题: {question}

请回答:
```

**Output Format**:
```json
{
  "answer": "ChatBI是...",
  "sources": [
    {"project": "ChatBI", "slide_no": 5, "similarity": 0.8234, "level": "slide"}
  ],
  "status": "success" | "no_context" | "error"
}
```

### 2. Create CLI Interface

**File**: `src/scripts/qa_cli.py`

**Command**: `python -m src.scripts.qa_cli`

**Options**:
- `--question, -q`: Question to ask (required)
- `--project, -p`: Filter by project name (optional)
- `--config`: Config file path (default: config/settings.yaml)
- `--top-k`: Retrieval top-k (default: 8)
- `--top-n`: Final results after rerank (default: 5)
- `--tau`: Similarity threshold (default: 0.5)

**Initialization**:
1. Load settings from YAML
2. Initialize M3EEmbedding
3. Initialize ChromaStore
4. Initialize LLMClient
5. Create QAEngine

**Output Display**:
```
问题: ChatBI的核心功能是什么

回答:
ChatBI是一个面向企业级的对话式商业智能平台...

来源:
  - ChatBI 第5页 (相似度: 0.8234, 级别: slide)
  - ChatBI 第1页 (相似度: 0.7891, 级别: slide)

状态: success
```

### 3. Create Package Init

**File**: `src/qa/__init__.py`

Export `QAEngine` for easy import:
```python
from .qa_engine import QAEngine

__all__ = ["QAEngine"]
```

## Critical Files

- **New Files**:
  - `src/qa/__init__.py` - Package initialization
  - `src/qa/qa_engine.py` - Core Q&A logic (~100 lines)
  - `src/scripts/qa_cli.py` - CLI interface (~80 lines)

- **Existing Files (No Changes)**:
  - `src/vectordb/chroma_store.py` - Uses `query_with_guardrails()`
  - `src/summarizer/llm_client.py` - Uses `generate()`
  - `src/config.py` - Uses existing settings

## Usage Examples

```bash
# Basic query
python -m src.scripts.qa_cli --question "ChatBI的核心功能是什么"

# Filter by project
python -m src.scripts.qa_cli -q "技术架构" -p ChatBI

# Custom retrieval parameters
python -m src.scripts.qa_cli -q "部署方式" --top-k 10 --top-n 3 --tau 0.6

# Use custom config
python -m src.scripts.qa_cli -q "API接口" --config config/prod_settings.yaml
```

## Error Handling

**Three Status Types**:
1. `success` - Normal answer with sources
2. `no_context` - No relevant documents found (below tau threshold)
3. `error` - LLM generation failure

**Graceful Degradation**:
- Empty retrieval results → "未找到相关内容，无法回答该问题。"
- LLM API errors → Caught and returned with error status
- Always returns structured output, never crashes

## Testing Strategy

**Manual Testing**:
```bash
# Test with existing data
python -m src.scripts.qa_cli -q "ChatBI是什么"

# Test no results (high threshold)
python -m src.scripts.qa_cli -q "irrelevant query" --tau 0.9

# Test with mock LLM (offline)
# Set llm_provider: mock in config
python -m src.scripts.qa_cli -q "test question"
```

**Unit Tests** (future):
- `tests/test_qa_engine.py` - Mock store and LLM
- Test success, no_context, and error paths

## Configuration

**Uses Existing Settings**:
- `llm_provider`, `llm_api_key`, `llm_model` - For LLM calls
- `vectordb_persist_dir`, `vectordb_collection_name` - For vector DB
- `embedding_model`, `embedding_device` - For embeddings

**No New Config Required** - All parameters have sensible defaults.

## Integration Points

**Existing Components**:
- `ChromaStore.query_with_guardrails()` - Retrieval with reranking and threshold
- `LLMClient.generate()` - Answer generation
- `M3EEmbedding` - Embedding model for queries
- `Settings.from_yaml()` - Configuration loading

**No Modifications Needed** - Pure additive design.

## Implementation Notes

1. **Prompt Language**: Chinese (matches existing pattern for Chinese PPTs)
2. **Citation Style**: Natural language in answer + structured sources list
3. **Minimal Code**: ~180 lines total for complete functionality
4. **Follows Patterns**: Matches existing codebase style (Pydantic, Click CLI, Chinese prompts)
5. **Extensible**: Easy to add features (streaming, multi-turn, custom prompts)
