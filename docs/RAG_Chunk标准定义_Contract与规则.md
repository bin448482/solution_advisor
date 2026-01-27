# RAG_Chunk标准定义_Contract与规则

日期：2026-01-12  
目标：定义“可复用、可导入”的 RAG chunk 标准，使不同项目都能基于同一套框架完成 RAG 知识沉淀（离线构建 + 在线检索）。

适用场景：以 PPT/文档为输入的企业知识资产（信息密、结构散、术语不统一），推荐采用 **Summary-first 分层检索**（RAPTOR 风格思想）以提升稳定性与一致性。

---

## 1. 为什么“chunks 化”要先定标准

“chunks 化”不是简单的切文本；它本质是在设计 **未来检索与回答时的上下文装配零件**：

- chunk 的粒度、密度、可追溯性，会直接决定检索稳定性、幻觉风险与成本。
- 不同项目想“直接导入框架”，必须先统一合同（contract）：什么是 chunk、必须带什么字段、怎么验证、怎么演进版本。

---

## 2. 推荐检索形态（决定 chunk 粒度）

默认推荐：**Summary-first 分层检索**（对齐 RAPTOR 思想，但不要求构建复杂树结构）

- 顶层（Project）：`overview`（口径统一、路由/概览）
- 中层（Category）：`category_summary`（主力检索单元，高密度、抗碎片化）
- 底层（Evidence）：`slide_evidence`（证据补充、引用支撑、核对）

> 可选增强：`qa_pair`、`metrics`、`topic`、`step` 等仅作为补充召回或对照回归，默认关闭。

---

## 3. Chunk 合同（Contract）：统一数据结构

每个 chunk 都必须是一个 `ChunkDocument`（JSON 对象），并组成 `rag_documents.json` 数组。

### 3.1 ChunkDocument：必备字段

- `id`：字符串，**稳定且唯一**
- `text`：字符串，**用于 embedding 的可读文本**（必须自洽）
- `metadata`：对象，**用于过滤/重排/追溯的结构化信息**
- `original_json`：可选（建议只存“来源索引/计数”等轻量信息，避免塞大段原文）

> 说明：本仓库当前的数据模型在 `src/rag/models.py`（`ChunkDocument` / `ChunkMetadata`）已具备雏形；标准化的目标是把“隐式约定”变成“显式合同 + 可验证门禁”。

### 3.2 metadata：跨项目通用必备字段（建议强制）

建议将以下字段视为“跨项目通用必备字段”（用于工程化与回归）：

- `project_name`: string
- `chunk_type`: string  
  允许值：`overview | category_summary | slide_evidence | qa_pair | metrics | step | topic`
- `level`: string  
  允许值：`project | category | slide`
- `rag_schema_version`: string（建议 `"v2"`）
- `source_slide_refs`: number[]（除 `overview` 外建议必填）
- `source_file` 或 `source_files`: string / string[]（与输入产物可对应）

工程化建议字段（强烈建议）：

- `ragprep_strategy`: `manual_import | map_reduce | compat_qa_pair`
- `ragprep_config_hash`: string（taxonomy + prompts + rules 的 hash，用于回归对比）

---

## 4. Chunk 类型标准（Type Specs）

### 4.1 `slide_evidence`（证据层，推荐作为标准类型）

用途：
- 回答时补证据与引用（降低无证据断言）
- 作为 CRAG（纠错检索）里的“证据是否充分”的依据

标准：
- 粒度：**1 slide = 1 chunk**（PPT 资产最稳，避免切碎）
- 长度：建议控制在 **200–500 中文字**（或 300–800 tokens 级别）
- `text` 结构建议固定：
  - `【Slide】{slide_no} {title}`
  - `【要点】...`
  - `【补充】...（必要时截断）`
- `metadata` 必带：
  - `chunk_type="slide_evidence"`, `level="slide"`
  - `slide_no`（建议新增该字段或沿用现有 `slide_no`）
  - `source_slide_refs=[slide_no]`
  - `source_file="page_summaries/{slide_no:03d}.json"`（或你们约定的同义路径）
  - 可选：`page_type`、`entities`、`confidence`

### 4.2 `category_summary`（类别层，主力检索单元）

用途：
- Summary-first 检索的主命中对象（高密度、稳定）
- 承担“跨页抽象”与“统一口径”

标准（与 `docs/generate_rag_documents.md` 对齐）：
- 一类一个 chunk：同项目内 `category_id` 唯一
- `metadata` 必带：
  - `chunk_type="category_summary"`, `level="category"`
  - `category_id`, `category_name`
  - `summary`：建议 **200–300 中文字**（由 rules 配置）
  - `qa_examples`：建议 **3–5 条**  
    每条包含：`question` / `answer` / `source_slide_refs`
  - `source_slide_refs`：该类别聚合来源 slide 列表（去重排序）
  - `source_files`：聚合来源文件列表（去重排序）
- `text` 建议固定拼接（用于 embedding）：
  - `【Category】{category_name} ({category_id})`
  - `【Summary】{summary}`
  - `【Representative Q&A】...`

### 4.3 `overview`（项目层）

用途：
- 项目整体口径、能力边界、定位与差异点的“权威摘要”
- 可作为 Self-RAG 思路的路由输入（先判断该搜哪些类别）

标准：
- 一项目一个 chunk（MVP 推荐 1 个）
- `metadata` 必带：`chunk_type="overview"`, `level="project"`
- 长度：建议 300–600 中文字（避免过长）
- 可选：`source_slide_refs` 为空或填“覆盖范围”（如 `[1..N]` 不建议真实写范围数组，避免膨胀）

### 4.4 可选增强类型（默认建议关闭）

> 这些类型在你们仓库已有实现或兼容逻辑（如 `qa_pair`、`metrics`、`topic`、`step`），但建议默认关闭，除非明确有收益/评测支撑。

- `qa_pair`：单问答检索，召回强但碎片化；适合作为“补召回”或对照组
- `metrics`：指标、性能、数值类内容可单独召回
- `topic/step`：主题/流程类（易漂移，且对 PPT 质量敏感）

约束：任何可选类型**必须**能回指来源（`source_slide_refs/source_file(s)`），否则会显著增加幻觉风险。

---

## 5. ID 规则（稳定可回归）

推荐统一 ID 规范（同项目同来源生成应尽量稳定）：

- `overview`：`{project_name}_overview`
- `category_summary`：`{project_name}_category_{category_id}`
- `slide_evidence`：`{project_name}_slide_{slide_no:03d}_evidence`
- `qa_pair`：`{project_name}_slide_{slide_no:03d}_qa_{idx:03d}`

---

## 6. 质量门禁（Validator 验收标准）

MVP 建议至少包含以下门禁（失败则不应写入正式 `embeddings/rag_documents.json`）：

### 6.1 结构与字段
- `rag_documents.json` 必须是 JSON 数组
- 每个元素必须有 `id/text/metadata`
- `metadata.chunk_type/level` 必须在允许集合
- `id` 必须全局唯一

### 6.2 追溯性（Traceability）
- `category_summary` / `slide_evidence` 必须有 `source_slide_refs`
- `source_files/source_file` 必须能对应到项目目录下的输入文件（如 `page_summaries/*.json`）

### 6.3 长度与密度
- 各类型 `text`、`summary`、`qa_examples` 的长度上限/下限必须满足 rules
- 防止超长 chunk 造成 embedding 语义稀释与检索不稳

### 6.4 覆盖度（Coverage）
- 至少包含 `category_summary`
- 建议包含 `overview`

输出建议：
- 生成 `ppt_outputs/<project>/ragprep/quality_report.json`（记录通过/失败原因、统计信息、配置 hash）

---

## 7. 标准如何工程化为“可导入框架”

为了让其他项目“直接导入框架”，建议将 chunk 标准拆成三类可复用工件：

1) **人读规范（本文件）**：清晰、可执行、能评审
2) **机器合同（schema/常量）**：例如 `schema_v2.json` 或 `schema_v2.py`（用于校验与版本演进）
3) **统一 validator**：把门禁变成代码，生成 `quality_report.json`，并在失败时阻止污染正式产物

此外，建议配套一个“模板包”（taxonomy + rules + prompts）：

```
ppt_outputs/<project>/ragprep/
  taxonomy.yaml     # 类别体系与别名（决定 category_summary 的分桶）
  rules.yaml        # 长度/必选类型/门禁阈值
  prompts/*         # map/reduce/overview/validate 的提示词
```

---

## 8. 与成熟范式的映射（论文思想 → 你们的标准）

- RAPTOR（分层摘要/多级检索）：`overview` + `category_summary` + `slide_evidence`
- CRAG（纠错检索）：用 `slide_evidence` 做证据补充；用门禁/评估器判断是否需要改写/扩检索
- Self-RAG（自检/路由）：用 `overview` 或“路由步骤”决定检索哪些 `category_id`
- HyDE（假想文档召回）：改变检索 query 的 embedding 输入，但最终回答仍必须由 `slide_evidence/category_summary` 支撑

---

## 9. 最小落地建议（MVP）

若要最小成本形成“跨项目可复用”的 chunks 标准，建议按顺序落地：

1) 固化合同：补齐 `rag_schema_version` 等必备字段（至少在 `metadata`）
2) 标准化三层 chunk：`overview`、`category_summary`、`slide_evidence`
3) 上线统一 validator + `quality_report.json`
4) 在线检索改为“两跳”：先摘要层，再证据层（可选）

