# RAG_MapMergeReduce_架构模式与模板规范

日期：2026-01-12  
目标：将 RAGPrep（自动知识沉淀）阶段的 **Map / Merge / Reduce** 设计架构化与模板化，形成“可导入框架”的工程模式：  
1) 标准化参数入口（Entry）与出口（Exit）  
2) 标准化中间工件（Artifacts）以便调试/回归/复用  
3) 标准化类别规范（Taxonomy）与未知类策略  
4) 标准化 prompt pack（模板）与可配置覆盖机制  

适用：本仓库 `src/rag/map_reduce_graph.py` 的演进与跨项目复用。

---

## 1. 总体架构模式（Pipeline Pattern）

将自动 RAGPrep 抽象为 5 个职责清晰、可替换的组件（可在 LangGraph 或普通函数式流水线中实现）：

1) **Batcher**：将 `page_summaries` 切分为 `batches`
2) **Mapper**：对每个 batch 生成“候选类别草稿”（local categories）
3) **Merger**：合并所有 batch 的草稿为“全局类别集合”（global categories）
4) **Reducer**：对每个 global category 生成最终 `category_summary` chunk（可并发）
5) **Emitter + Validator**：校验、写出 `rag_documents.json` + `quality_report.json`（失败不污染正式产物）

> 设计原则：**确定性优先，LLM 兜底**；结构化输出优先，便于回归与调试。

---

## 2. 标准化参数入口（Entry）

为可复用与跨项目移植，建议将参数入口拆成两层，并在运行时合并为“最终生效配置”。

### 2.1 Runtime 参数（工程运行参数）

建议继续通过 `config/settings.yaml`（或 `src/config.py` 的 `Settings`）管理：

- `auto_ragprep_enabled`：是否启用自动 RAGPrep
- `map_batch_size`：Map 批大小（页数）
- `map_max_categories_per_batch`：Map 阶段每批最多类别数
- `reduce_target_categories`：全局类别数上限（用于 Merge 裁剪）
- `langgraph_max_concurrency`：Map/Reduce 并发度
- `map_temperature` / `reduce_temperature`：LLM 温度

### 2.2 Spec 参数（知识工程规范参数，模板化）

建议通过项目模板包管理（见第 6 节 `ragprep/`）：

- `taxonomy.yaml`：类别规范、别名映射、未知类策略
- `rules.yaml`：chunk 标准（summary/qa_examples 的长度与数量）、必选 chunk 类型、门禁阈值
- `prompts/*.txt`：map/reduce/overview/validate 的 prompt pack

### 2.3 生效配置（Merged Config）

建议在每次运行生成以下信息（用于回归）：

- `ragprep_strategy`：`map_reduce`
- `rag_schema_version`：例如 `"v2"`
- `ragprep_config_hash`：对 taxonomy + rules + prompts 计算 hash（用于定位差异）

并写入：

- `ppt_outputs/<project>/ragprep/effective_config.json`（可选）

---

## 3. 标准化参数出口（Exit）

为了模块化开发与可复盘，建议定义稳定的出口工件（Artifacts），并提供可选落盘。

### 3.1 必备产物（对外合同）

- `ppt_outputs/<project>/embeddings/rag_documents.json`  
  最终 RAG chunks（通过门禁才写入/覆盖）

### 3.2 必备报告（永远写）

- `ppt_outputs/<project>/ragprep/quality_report.json`  
  校验结果、统计信息、失败原因、配置 hash、运行参数快照

### 3.3 建议的中间工件（用于调试/回归/复用）

- `ppt_outputs/<project>/ragprep/map_outputs.jsonl`：每行一个 `MapOutput`
- `ppt_outputs/<project>/ragprep/merge_output.json`：一个 `MergeOutput`
- `ppt_outputs/<project>/ragprep/reduce_outputs.jsonl`：每行一个 `ReduceOutput`
- `ppt_outputs/<project>/ragprep/errors.jsonl`：结构化错误流（可选）

> 说明：中间工件建议默认写入（或提供开关），这是“工程化沉淀”的关键抓手。

---

## 4. 阶段划分与 IO 合同（Stage Contracts）

本节定义 Map / Merge / Reduce 的输入输出标准，便于模块化实现、单测与跨项目复用。

### 4.1 Map 阶段

#### MapInput（每个 batch）

最小字段（示意）：

```json
{
  "project_name": "ChatBI产品介绍_2025",
  "batch_id": "batch_001",
  "slides": [
    {
      "slide_no": 1,
      "title": "…",
      "one_liner": "…",
      "bullets": ["…"],
      "details": "…",
      "entities": ["…"],
      "confidence": 0.83
    }
  ],
  "taxonomy_version": "2026-01-12",
  "ragprep_config_hash": "..."
}
```

#### MapOutput（每个 batch）

目标：输出“候选类别草稿”，并强制归一为 taxonomy 的 `category_id`。

```json
{
  "batch_id": "batch_001",
  "local_categories": [
    {
      "category_id": "features",
      "category_name": "功能特性",
      "evidence_slide_refs": [1, 3, 5],
      "key_points": ["…", "…"],
      "confidence": 0.7
    }
  ],
  "errors": []
}
```

Map 阶段开发建议：
- **优先规则/启发式**：如果能从 `PageSummary` 的 signals/page_type/entities 推断类别，则尽量不调用 LLM
- LLM 仅补齐：无法判定类别、或需要抽取 key_points 时调用
- 输出必须严格 JSON，且 `category_id` 必须来自 taxonomy（不能自由造类）

### 4.2 Merge 阶段

目标：把所有 MapOutput 合并为“全局类别集合”，并处理：
- 归一（alias → 标准 `category_id`）
- 去重（slides、points）
- 裁剪（超过目标类别数时的策略）
- 冲突（一个 slide 落多类的处理策略）

#### MergeOutput

```json
{
  "global_categories": [
    {
      "category_id": "features",
      "category_name": "功能特性",
      "source_slide_refs": [1, 3, 5, 7],
      "supporting_points": ["…", "…"],
      "coverage": { "slide_count": 4, "batch_count": 2 }
    }
  ],
  "dropped": [
    { "reason": "over_target_categories", "category_id": "misc" }
  ],
  "errors": []
}
```

Merge 阶段开发建议（**确定性优先**）：
1) `normalize`：通过 taxonomy aliases 将 `category_name` 映射到标准 `category_id`
2) `union_slides`：合并 slide refs 去重排序
3) `merge_points`：要点去重（可用简单相似度/规则）
4) `cap_categories`：超过 `reduce_target_categories` 时，按覆盖度/置信度/重要性裁剪
5) 仅在“无法归一/冲突严重”时调用 LLM 做裁决（可选开关）

### 4.3 Reduce 阶段

目标：针对每个 global category 生成最终的 `category_summary` chunk（对齐 chunk 合同与门禁）。

#### ReduceInput（单个类别）

```json
{
  "category_id": "features",
  "category_name": "功能特性",
  "source_slide_refs": [1, 3, 5, 7],
  "supporting_points": ["…", "…"],
  "ragprep_config_hash": "..."
}
```

#### ReduceOutput（单个类别）

```json
{
  "category_id": "features",
  "chunk": {
    "id": "ChatBI产品介绍_2025_category_features",
    "text": "…",
    "metadata": { "chunk_type": "category_summary", "level": "category", "…" },
    "original_json": "…"
  },
  "errors": []
}
```

Reduce 阶段开发建议：
- 输入必须包含可追溯来源（slide refs + files）
- 输出必须满足 rules：summary 长度、qa_examples 数量、引用完整性
- 可并发执行，但要保证输出稳定（排序、去重）

---

## 5. 类别规范（Taxonomy）标准

Taxonomy 是 Map/Merge/Reduce 的“共同语言”，必须作为“一等公民”被标准化与外置化。

### 5.1 Taxonomy 的最小结构

建议 `taxonomy.yaml` 至少包含：

- `taxonomy_version`
- `categories`: 标准类别表（`id/name/description`）
- `aliases`: 别名映射（string → category_id）
- `unknown_policy`: 未知类处理策略
- `target_max_categories`: 全局类别上限（与 `reduce_target_categories` 对齐或作为上限约束）

### 5.2 标准类别（建议默认 8 类）

建议默认沿用本仓库现有 8 类（跨项目通用，且与现有实现兼容）：

- `positioning`：产品定位/价值
- `features`：功能特性/能力
- `architecture`：技术架构/系统设计
- `integration`：集成对接/API/数据接入
- `deployment`：部署/交付/运维
- `cases`：客户案例/POC
- `comparison`：竞品对比/差异化
- `roadmap`：产品规划/路线图

> 是否允许项目自定义类别数：建议支持，但必须通过 taxonomy 明确声明，且必须提供 aliases 与边界说明，避免类别漂移。

### 5.3 未知类策略（unknown_policy）

推荐选项：
- `bucket_to_misc`：归入 `misc`（前提是 taxonomy 明确包含 `misc` 类）
- `drop`：直接丢弃（保守，避免污染）
- `force_map_with_llm`：调用 LLM 强制映射（成本高但覆盖强）

MVP 建议：**`drop` 或 `bucket_to_misc`**（优先稳定）。

---

## 6. 模板包（Template Pack）规范

为了让其他项目“直接导入框架”，建议将可变部分集中到项目模板包目录：

```
ppt_outputs/<project>/
  ragprep/
    taxonomy.yaml
    rules.yaml
    prompts/
      map.txt
      reduce.txt
      overview.txt
      validate.txt
    map_outputs.jsonl
    merge_output.json
    reduce_outputs.jsonl
    quality_report.json
```

### 6.1 rules.yaml（门禁与规格）

建议字段：
- `required_chunk_types`: `["category_summary", "overview"]`
- `category_summary.summary_length_cn`: `{min: 200, max: 300}`
- `category_summary.qa_examples`: `{min: 3, max: 5}`
- `text_length_limits`: 各 chunk_type 的 text 长度上限
- `validator_thresholds`: 去重阈值、最低覆盖、最小相似度等

### 6.2 prompts/*.txt（prompt pack）

设计目标：**可替换、可版本化、可对照回归**。

硬性要求：
- 输出必须是严格 JSON（契约字段齐全）
- 禁止编造：所有事实必须可由 slide summaries 支撑
- 必须输出 `source_slide_refs`（用于引用与门禁）
- `category_id` 必须来自 taxonomy（不能自由造类）

建议把 prompt 与版本写入 `quality_report.json`，用于回归定位。

---

## 7. 标准化“入口/出口”在代码中的建议实现方式

### 7.1 模块边界建议

- `ragprep/config_loader.py`：读取并合并 runtime + spec，生成 effective config + hash
- `ragprep/contracts.py`：Map/Merge/Reduce 的 Pydantic 模型（或 TypedDict）
- `ragprep/batcher.py`：batch 切分策略
- `ragprep/mapper.py`：规则优先 + LLM 兜底的 Map 实现
- `ragprep/merger.py`：确定性 Merge 实现（可选 LLM 仲裁）
- `ragprep/reducer.py`：Reduce 生成 `category_summary`
- `ragprep/emitter.py`：落盘 `rag_documents.json`（通过门禁才写）
- `ragprep/validator.py`：统一门禁与 `quality_report.json`

> LangGraph 仅作为调度器：节点调用以上模块即可，避免业务逻辑都写在 graph 文件里。

### 7.2 与现有代码的衔接点

- `src/pipeline.py` 的 `RAGPrepStage`：只负责选择策略与调用入口（manual vs map-reduce）
- `src/rag/map_reduce_graph.py`：逐步瘦身为“图调度 + 调用模块”
- `src/rag/models.py`：继续作为最终 `ChunkDocument/ChunkMetadata` 合同（并补齐 schema_version/strategy/hash）

---

## 8. MVP 验收标准（架构模式是否“可导入复用”）

- 同一套 `ragprep/` 模板包可在另一个项目目录下直接运行并产出 `rag_documents.json`
- Map/Merge/Reduce 每阶段都有稳定输出工件（至少内存结构稳定，建议落盘）
- 入口参数（runtime + spec）有明确覆盖优先级与 effective_config 记录
- taxonomy 可替换，且 `category_id` 强制归一（无自由造类）
- 失败不污染正式产物：只有通过门禁才写 `embeddings/rag_documents.json`

