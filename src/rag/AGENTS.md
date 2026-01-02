# RAG Package (src/rag/)

## 职责概述

RAG v2 包实现基于 QA 对的多类型 chunk 生成策略，用于优化向量检索质量。

## 核心模块

### models.py
- **数据模型**：`Category`（8 类枚举）、`QAPair`、`ChunkDocument`、`ChunkMetadata`
- **辅助函数**：`get_category_name()` 获取中文类别名

### qa_generator.py
- **入口**：`QAGenerator.generate_qa_pairs(summary, project_name) -> List[QAPair]`
- **功能**：从 PageSummary 生成 5-10 个问答对
- **配置**：`min_confidence=0.3`（过滤低置信度问答）
- **重试**：3 次指数退避（1s, 2s, 4s）

### classifier.py
- **入口**：`LLMClassifier.batch_classify(qa_pairs, project_name) -> List[Category]`
- **功能**：批量分类问答对到 8 个类别
- **配置**：`batch_size=8`（每批 8-10 个问答对）
- **优化**：批处理降低 80% 成本

### chunk_generator.py
- **入口**：
  - `generate_qa_chunks(qa_pairs, project_name) -> List[ChunkDocument]`
  - `generate_topic_chunks(summary, project_name) -> List[ChunkDocument]`
  - `generate_step_chunks(summary, project_name) -> List[ChunkDocument]`
  - `generate_metrics_chunks(summary, project_name) -> List[ChunkDocument]`
  - `generate_overview_chunk(profile, project_name) -> ChunkDocument`
  - `decide_chunk_types(summary) -> List[str]`（决策逻辑）
- **功能**：生成多种类型的 chunk（qa_pair/topic/step/metrics/overview）

### legacy.py
- **原有逻辑**：单 chunk 生成（已弃用，保留用于参考）
- **函数**：`prepare_slide_embedding()`, `prepare_project_embedding()`, `clean_summary_for_embedding()`

## 关键依赖

- `src.models.PageSummary`, `ProjectProfile`
- `src.summarizer.llm_client.LLMClient`
- `src.rag.legacy._classify_page_types`（规则分类）

## 配置项

- **QA 生成**：`min_confidence=0.3`（最低置信度）
- **批量分类**：`batch_size=8`（批大小）
- **Chunk 决策**：基于关键词检测（步骤/指标/主题）

## 运行与测试

### 单元测试
```bash
pytest tests/test_qa_generator.py -v
pytest tests/test_classifier.py -v
pytest tests/test_chunk_generator.py -v
```

### 集成测试
```bash
# 通过 pipeline 运行
python -m src --input ppts/demo.pptx --output ppt_outputs/demo --force
```

### 输出验证
```bash
# 检查生成的 chunk 数量和类型
cat ppt_outputs/demo/embeddings/rag_documents.json | jq '.[] | .metadata.chunk_type' | sort | uniq -c
```

## 错误处理

- **QA 生成失败**：记录到 manifest.errors（stage=qa_generation）
- **分类失败**：保留原有类别（基于关键词推断）
- **Chunk 生成失败**：跳过该 chunk，继续处理

## 性能指标

- **Token 消耗**：每页约 2050 tokens（QA 生成 1800 + 分类 250）
- **成本**：GPT-4o 约 $0.015/页，GPT-4o-mini 约 $0.013/页
- **并发**：QA 生成支持并行（max_workers=3）
- **批处理**：分类批量处理（8-10 个/批）

## 变更记录

- 2026-01-02：实现 RAG v2（QA-pair 方案），替换单 chunk 策略
