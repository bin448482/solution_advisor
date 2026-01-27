# RAG阶段_架构化与模板化_MVP实施计划

日期：2026-01-12  
范围：`src/pipeline.py` 的 `RAGPrepStage` 及其产物 `ppt_outputs/<project>/embeddings/rag_documents.json`

---

## 背景与现状

当前仓库的 RAG 资产生成分为两条路径：

- **人工高质量（默认）**：`config.Settings.auto_ragprep_enabled=false` 时，流水线不会自动生成 `embeddings/rag_documents.json`，需要按 `docs/generate_rag_documents.md` 产出后复跑或用 `src/scripts/vectordb_cli.py import-docs` 入库。
- **自动生成（可选）**：`auto_ragprep_enabled=true` 时，走 `src/rag/map_reduce_graph.py`（LangGraph Map-Reduce）自动生成以 `category_summary + overview` 为主的 `rag_documents.json` 并落盘。

资产结构“合同”目前主要由以下代码隐式定义：

- `src/rag/models.py`：`ChunkDocument` / `ChunkMetadata`（chunk schema）
- `src/rag/map_reduce_graph.py`：类别体系与别名、Map/Reduce 节点、校验与落盘
- `docs/generate_rag_documents.md`：人工产物的字段约束、聚合口径与质量要求

现阶段的主要痛点：

- **规则/类别/提示词分散且部分写死在代码里**（尤其是 `map_reduce_graph.py` 的标准类别与别名映射）。
- **“人工”和“自动”属于两套并行流程**，对齐靠约定，难以回归和系统演进。
- **缺少可复用的项目级模板包**：换新项目时只能复制经验，而不是复用配置与校验门禁。

---

## 目标（架构化 + 模板化）

### 目标 1：架构化（Strategy/Plugin 化）

把 RAG 阶段抽象成统一接口：同一输入（`page_summaries` + `project_profile`），不同构建策略（人工导入 / Map-Reduce / 兼容 QA-pair）都产出同一合同的 `rag_documents.json`。

### 目标 2：模板化（Project Pack）

为每个项目提供一套“可编辑、可复用、可校验”的 RAG 模板包（taxonomy + prompts + rules + quality report），把经验固化为文件，而不是固化在人的脑子或代码分支里。

### 目标 3：可回归与可控

引入明确的质量门禁与产物版本，确保：

- 产物结构稳定（schema/version）
- 引用可追溯（`source_slide_refs` / `source_files`）
- 失败可解释可回退（errors + report）

---

## 设计原则

- **Manual-first 不变**：默认仍是人工高质量路径，自动只是可选能力（批处理/草稿/大规模摄取）。
- **合同先行**：把 `rag_documents.json` 作为唯一对外合同，所有策略都必须输出同样的结构与最小字段集合。
- **配置外置**：taxonomy、prompt pack、规则与校验都应可通过文件配置替换，而不是改代码。
- **渐进落地**：先做到“结构统一 + 模板包 + 门禁报告”，再演进更复杂的策略与评测体系。

---

## 核心抽象（建议）

> 下面是建议新增的抽象层，不要求一次性完成，但建议按该方向收敛。

### 1) RAGPrep Builder 接口

统一签名（示意）：

- 输入：`summaries: List[PageSummary]`、`profile: ProjectProfile | None`、`project_name: str`
- 输出：`rag_docs: List[dict]`、`errors: List[dict]`、`report: dict`

策略实现（建议至少三类）：

- `ManualImportBuilder`：如果存在 `ppt_outputs/<project>/embeddings/rag_documents.json`，直接加载并校验；否则输出“缺失提示 + 下一步动作”。
- `MapReduceBuilder`：包装 `src/rag/map_reduce_graph.py`，并允许从模板包加载 taxonomy 与 prompt pack。
- `CompatQAPairBuilder`（可选）：沿用 `src/rag/chunk_generator.py` 的 QA-pair/metrics 等兼容 chunk（受开关控制），用于保留旧路径/对照回归。

### 2) Contract & Version

建议为所有 chunk 增加最小公共字段（在 `metadata` 内即可）：

- `rag_schema_version`: `"v2"`（或语义化版本，如 `"2.0"`）
- `ragprep_strategy`: `"manual_import" | "map_reduce" | "compat_qa_pair"`
- `ragprep_config_hash`: taxonomy + prompts + rules 的 hash（用于回归与定位差异）

### 3) Validator（质量门禁）

把校验从策略内部抽出来，形成统一 validator：

- 结构校验：必须是数组；每个元素必须含 `id` / `text` / `metadata.project_name` / `metadata.chunk_type` / `metadata.level`
- 追溯校验：`category_summary` 必须有 `source_slide_refs` + `source_files` 且能对应到 `page_summaries/*.json`
- 长度/密度：`text`、`summary`、`qa_examples` 的上限/下限
- 去重：相同 `id`/高度相似文本的重复检测
- 覆盖度：至少包含 `category_summary`；建议包含 `overview`

校验结果写入：

- `ppt_outputs/<project>/ragprep/quality_report.json`

---

## 模板包（Project Pack）结构

建议为每个项目新增一个“RAG 模板包目录”，与 `embeddings/` 并列，便于人工编辑与自动加载。

推荐结构：

```
ppt_outputs/<project>/
  ragprep/
    taxonomy.yaml
    prompts/
      map.txt
      reduce.txt
      overview.txt
      validate.txt
    rules.yaml
    quality_report.json          # 生成产物（可选提交）
```

### taxonomy.yaml（类别体系）

目标：把 `src/rag/map_reduce_graph.py` 内的 `_standard_categories` / `_category_alias` 外置化，并允许项目定制。

建议字段：

- `categories`: 标准类目（`id`/`name`/`description`/`examples`）
- `aliases`: 别名 → 标准 id
- `target_max_categories`: 全局类别上限（对齐 `Settings.reduce_target_categories`）

### rules.yaml（聚合口径与门禁）

建议字段：

- `required_chunk_types`: `["category_summary", "overview"]`
- `category_summary.summary_length_cn`: 200-300
- `category_summary.qa_examples_range`: 3-5
- `require_traceability`: true
- `id_prefix`: `<project_name>`

### prompt pack（提示词模板）

目标：让不同项目/不同 LLM 具备可替换提示词，而不是改代码。

基本要求：

- 模板中必须强调“禁止编造”“引用 slide refs”“输出严格 JSON 结构”
- map/reduce 的输出结构与 `rag_documents.json` 合同对齐

---

## 建议的流水线行为（对齐现有实现）

### 1) 默认路径（人工优先）

- `python -m src ...` 在 `RAGPrepStage` 检测 `ppt_outputs/<project>/embeddings/rag_documents.json`
  - 存在：加载 → 校验 → 入库（如启用 vectordb）
  - 不存在：给出明确提示并退出该 stage（现有行为保持）

### 2) 自动路径（Map-Reduce）

- `auto_ragprep_enabled=true` 时：
  - 读取 `ppt_outputs/<project>/ragprep/`（若存在）作为 taxonomy + prompts + rules
  - 否则使用内置默认模板（与 `docs/generate_rag_documents.md` 对齐）
  - 生成 `ppt_outputs/<project>/embeddings/rag_documents.json`
  - 生成 `ppt_outputs/<project>/ragprep/quality_report.json`

### 3) 回退策略

- Map/Reduce 失败不应直接污染正式 `rag_documents.json`：
  - 建议：失败输出写入 `ragprep/quality_report.json`，并在 `manifest.errors` 记录；只有通过门禁才写入 `embeddings/rag_documents.json`
  - 或：写入 `embeddings/rag_documents.draft.json`，由人工确认后替换

---

## 配置建议（Settings 对齐）

现有关键配置在 `src/config.py`：

- `auto_ragprep_enabled`（总开关）
- `map_batch_size` / `map_max_categories_per_batch`
- `reduce_target_categories`
- `langgraph_max_concurrency`
- `map_temperature` / `reduce_temperature`
- 兼容性开关：`enable_llm_classify` / `enable_topic_chunks` / `enable_step_chunks` / `enable_metrics_chunks`

建议新增（或通过 rules.yaml 代替）：

- `ragprep_templates_dir`：默认 `ppt_outputs/<project>/ragprep`
- `rag_schema_version`：默认 `"v2"`
- `ragprep_write_draft_on_fail`：默认 `true`

---

## 验收标准（MVP）

MVP 以“可复用模板 + 统一门禁 + 策略可切换”为验收重点：

- 统一输出合同：不论人工/自动，最终都产出同结构的 `ppt_outputs/<project>/embeddings/rag_documents.json`
- 模板包可用：每个项目可通过 `ppt_outputs/<project>/ragprep/` 覆盖 taxonomy/prompts/rules
- 质量门禁可用：生成 `ppt_outputs/<project>/ragprep/quality_report.json`，并在失败时阻止写入正式 `rag_documents.json`
- 可回归：`metadata` 内包含 `ragprep_strategy` 与 `ragprep_config_hash`，便于对比两次产物差异

---

## 实施步骤（建议分两期）

### Phase 1（1-2 天）：模板包 + 门禁

- 把 `src/rag/map_reduce_graph.py` 的类别体系与别名外置为 taxonomy（默认内置 + 可选覆盖）
- 抽出 validator，生成 `ragprep/quality_report.json`
- 写出 rules.yaml 的默认值并对齐 `docs/generate_rag_documents.md`

### Phase 2（2-4 天）：策略接口统一

- 引入 Builder 接口与 registry（strategy/plugin）
- `RAGPrepStage` 只负责选择策略 + 调用 + 落盘/入库
- 可选引入 `draft` 产物与人工确认流程

---

## 风险与对策

- **风险：模板配置导致产物不一致**  
  对策：强制写入 `ragprep_config_hash`，并在 report 中记录生效的 taxonomy/rules/prompt 版本。

- **风险：自动产物质量波动**  
  对策：默认 manual-first；自动产物必须过门禁；失败写 draft 并要求人工 review。

- **风险：兼容历史 chunk 类型导致检索行为漂移**  
  对策：MVP 聚焦 `category_summary + overview`；其他 chunk 类型保持开关默认关闭，必要时仅用于 A/B 对照。

