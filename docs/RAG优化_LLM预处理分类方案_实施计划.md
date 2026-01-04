# RAG 优化：LLM 预处理分类实施计划（重写版）

**日期**：2026-01-03  
**适用项目**：`ChatBI产品介绍_2025` 及后续同类 PPT 项  
**输入来源**：`ppt_outputs/<项目>/page_summaries/*.json`（单页总结，已与 slides 对齐）  
**核心目标**：在“知识沉淀”阶段按类别生成高质量摘要与问答，降低对纯向量相似度的依赖，提升命中与可控性。

---

## 1. 目标与痛点
- 现状：直接把每页 QA/metrics 送入向量库，依赖相似度；对问题语义、专业词的理解不足，导致召回噪声和回答不理想。
- 目标：先按 **Category** 聚合 `page_summaries`，用 LLM 生成“类别权威摘要 + 代表问答”，再入库。这样检索优先命中“按类沉淀的知识块”，而非零散页粒度。

## 2. 新版输出物
- `ppt_outputs/<项目>/embeddings/rag_documents.json`
  - `category_summary`：每个 Category 1 条，LLM 基于该类相关的 `page_summaries` 生成摘要+精选问答。
  - `qa_pair`：保留单页 QA（可选，用于细粒度补充）。
  - `metrics`：结构化指标块（数值问答）。
  - `overview`：项目级画像。
- `ppt_outputs/<项目>/embeddings/manifest` 同步计数，供质检。

## 3. Chunk 设计
| chunk_type | 粒度 | 内容 | 生成方式 | 用途 |
| --- | --- | --- | --- | --- |
| category_summary（新增主力） | category | 该类的权威摘要 + 3~5 代表问答（问/答各 80~200 字） | LLM 聚合同类 `page_summaries` | 主力检索、冷启动 |
| qa_pair（次要） | slide | 单页 QA，对应来源页 | LLM/Mock 每页生成 | 细粒度补充 |
| metrics | slide | 指标/表格摘要，`metric_items` | 规则+LLM | 数值问答 |
| overview | project | 项目画像 | LLM | 全局语境 |

## 4. 元数据模型（关键字段）
- 通用：`project_name`, `chunk_type`, `level`, `category_id/name?`, `source_slide_refs`, `source_file|source_files`.
- `category_summary`：
  - `level="category"`, `category_id/name` 必填
  - `source_files`: 参与聚合的 `page_summaries/*.json`
  - `metadata.summary`: 类别摘要正文（与 `text` 同步存储，便于下游只读元数据）
  - `metadata.qa_examples`: 代表问答列表（问题、答案截断、来源 slide_no）
- QA/metrics/overview 沿用现有字段，`original_json` 精简为来源信息（不再全量序列化）。

## 5. 处理流程（新版）
1) **Capture/Extract/Interpret**：保持现有步骤，得到 `slides/` 与 `page_summaries/`。  
2) **聚类分桶**：依据 `PageSummary.entities/signals/title` 粗分到 8 类 Category（规则 + 可选 LLM classifier）。  
3) **Category 摘要生成**（新增主线）  
   - 输入：同一 Category 的 `page_summaries` 原文（标题/要点/细节）。  
   - 调用 LLM 生成：
     - `summary`：该类的 200~300 字权威摘要。  
     - `qa_examples`：3~5 条高价值问答，覆盖不同子主题，附 `source_slide_refs`。  
   - 产出 `category_summary` chunk。  
4) **QA/metrics/overview**：可配置保留，按原逻辑生成。  
5) **写出 rag_documents.json**：所有 chunk，`metadata` 中存 `summary`/`qa_examples`（仅 category_summary）与来源信息。  
6) **向量入库**：`ChromaStore` upsert，`documents` 用 `text`，`metadatas` 记录 `chunk_type`、`category_id` 等。  

## 6. 配置与开关
- `enable_category_summary_chunks`（默认开）：生成类别摘要（主力）。  
- `enable_llm_classify`：是否用 LLM 分类 PageSummary（否则规则分桶）。  
- `enable_topic_chunks` / `enable_step_chunks`：保持关闭（legacy）。  
- `enable_metrics_chunks`：可选开关。  

## 7. 质量与验证
- 覆盖度：每个有内容的 Category 必须生成 1 条 `category_summary`。  
- 长度：摘要 200~300 字；每条 QA 答案 ≤200 字。  
- 追溯：`source_files`/`source_slide_refs` 必填，便于质检。  
- 验证脚本（待实现）：统计 chunk 数、字段完整性，抽查相似度查询命中率；人工抽样 10% 比对原文。  

## 8. 发布与回滚
- 双写期：生成新 rag 文档 + 新 collection；检索先灰度切到 `category_summary` 优先（QA 作补充）。  
- 回滚：关闭 `enable_category_summary_chunks`，恢复旧 QA-only 策略；保留旧向量集合。  

## 9. 资源与成本
- Category 汇总调用量：按 8 类计，每类 1 次；比逐页分类大幅降成本。  
- 模型建议：摘要用 GPT-4o-mini / Claude-Haiku；QA 生成可复用同一模型；temperature 0.1 保持稳定。  

---

**状态**：实施计划（已确认方向，可立即开发）  
**待办**：实现新的聚合/摘要流水线、验证脚本，并更新 AGENTS/README。
