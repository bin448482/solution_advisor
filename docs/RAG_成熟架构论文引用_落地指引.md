# RAG_成熟架构论文引用_落地指引

日期：2026-01-12  
适用仓库：Solution Advisor（PPT → `rag_documents.json` → Chroma → QA）

本文整理“可直接引用的成熟 RAG 架构/论文”，并给出在本项目内的**具体落地做法**（尽量复用现有模块：`src/pipeline.py`、`src/rag/map_reduce_graph.py`、`src/vectordb/chroma_store.py`、`src/qa/qa_engine.py`）。

---

## 一、你们当前的 RAG 形态（用于对照）

- **离线知识资产**：`ppt_outputs/<project>/embeddings/rag_documents.json`（主力为 `category_summary + overview`；可选兼容 `qa_pair/metrics/...`）
- **离线生成**：默认人工（`docs/generate_rag_documents.md`），可选 LangGraph Map-Reduce（`src/rag/map_reduce_graph.py`）
- **在线检索**：Chroma（`src/vectordb/chroma_store.py`，含 `query_with_guardrails` / `query_with_qa_ranking`）
- **在线问答**：`src/qa/qa_engine.py`（检索 → prompt → LLM 生成）

因此，你们最适合“直接套用”的成熟范式是：**分层（summary-first）检索 + 纠错循环（re-retrieve）+ 可回归评测**。

---

## 二、核心可引用论文（架构范式）

### 1) RAPTOR：分层摘要/聚类 → 多层级检索

- 论文：**RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval**（arXiv:2401.18059）  
  链接：`https://arxiv.org/abs/2401.18059`

可引用点（范式摘要）：
- 先把原始文档组织成“多层抽象结构（树/层级）”，检索时可在不同层级选择证据，提升覆盖与稳定性。

在本项目的落地方式（最小实现）：
- 你们现有 `overview（project）` + `category_summary（category）` + `slide（evidence，可选）` 已是“RAPTOR 风格分层”的简化实现。
- 建议把在线检索改成“两跳/两层”：
  1) **第一跳只检索高密度层**：限定 `metadata.level in {"project","category"}` 或 `chunk_type in {"overview","category_summary"}`，返回少量“类别摘要”。
  2) **第二跳补充证据页**：从命中的 `metadata.source_slide_refs` 派生出 slide_no 列表，再检索/筛选 slide chunk（或直接从 `page_summaries/<no>.json` 拼证据）。
- 代码改动主要集中在：
  - `src/vectordb/chroma_store.py`：支持按 `chunk_type/level` 过滤检索；支持按 `slide_no` 精确过滤/补召回（如果 slide chunk 也入库）。
  - `src/qa/qa_engine.py`：组装 context 时优先摘要层，再追加少量证据层。

### 2) CRAG：先评估检索质量 → 再决定纠错动作

- 论文：**Corrective Retrieval Augmented Generation**（arXiv:2401.15884）  
  链接：`https://arxiv.org/abs/2401.15884`

可引用点（范式摘要）：
- 不把一次检索当作终局：先判断“检索是否足够好”，不足则触发改写/扩检索/换检索源等纠错步骤。

在本项目的落地方式（最小实现，CRAG-lite）：
- 在 `src/qa/qa_engine.py` 的一次回答中引入“检索质量判定器（Evaluator）”：
  - 规则版（低成本）：top-1 相似度 < `tau`、top-k 相似度整体偏低、命中 chunk_type 全是 slide 且缺少 category_summary 等情况 → 触发纠错。
  - LLM 版（更准）：让 LLM 判断“这些检索片段是否足以回答问题？缺什么？”输出结构化 JSON：`{verdict, missing_aspects, rewrite_queries[]}`
- 纠错动作建议按成本从低到高：
  1) query 改写（多写法/补关键字）→ 重检索
  2) 限定只搜 `category_summary` → 再搜 slide 证据（与上面的 RAPTOR 两跳融合）
  3) 更大 top_k 或放宽/收紧 `tau`（按缺口动态调参）

### 3) Self-RAG：生成过程自检（是否需要检索/证据是否支撑）

- 论文：**Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection**（arXiv:2310.11511）  
  链接：`https://arxiv.org/abs/2310.11511`

可引用点（范式摘要）：
- 将“是否检索/检索后是否足够/生成是否被证据支撑”的决策显式化，降低无证据输出带来的幻觉。

在本项目的落地方式（不训练，工程化复刻思路）：
- 在回答前增加一个“路由/计划”步骤（可复用你们的引导式对话能力 `src/qa/dialogue_orchestrator.py` 的结构输出习惯）：
  - 第一步：让 LLM 输出 `needs_retrieval: bool`、`target_categories[]`、`key_terms[]`
  - 第二步：按 `target_categories` 做检索与组装 context
  - 第三步：回答时强制“基于检索片段作答”，并输出引用（chunk ids / slide refs）

### 4) HyDE：生成“假想相关文档”做向量召回

- 论文：**Precise Zero-Shot Dense Retrieval without Relevance Labels**（HyDE，arXiv:2212.10496）  
  链接：`https://arxiv.org/abs/2212.10496`

可引用点（范式摘要）：
- 先让 LLM 生成一段“假想答案/假想文档”，再用其 embedding 去检索真实语料邻域，缓解“用户问法与语料表达不一致”导致的召回问题。

在本项目的落地方式（最小实现）：
- 在 `src/qa/qa_engine.py` 里加入 HyDE 模式（可用开关控制）：
  1) 输入用户问题 `q`
  2) 生成一段“理想答案段落” `d_hat`（强调：仅用于检索，不作为最终答案）
  3) 用 `d_hat` 做 embedding 检索（或将 `q` 与 `d_hat` 双检索融合重排）
  4) 最终回答必须以检索证据为准（可与 CRAG 的“证据充足判定”配合）

---

## 三、评测与回归（工程落地，建议引用的成熟工具）

> 评测不属于“RAG 架构论文”，但属于“成熟可复用方案”，建议和上面的架构一起写进实施方案与验收标准。

### 1) Ragas：RAG pipeline 评测框架（快速跑通）

- 文档：`https://docs.ragas.io/en/latest/`  
  `evaluate()` 参考：`https://docs.ragas.io/en/latest/references/evaluate/`

在本项目的落地方式：
- 将 `logs/qa_sessions/*.jsonl` 或一组“黄金问题集”（question + expected/ground_truth 可选）转成数据集；
- 用 Ragas 跑批评测，做版本对比（如不同 `top_k/top_n/tau`、是否启用 HyDE/两跳检索）。

### 2) RAGChecker：claim-level 诊断（定位问题根因）

- 项目：`https://github.com/amazon-science/RAGChecker`

在本项目的落地方式：
- 把回答拆成 claims，结合检索证据判断“是否有支撑/是否过度推断”，用于诊断：
  - 是召回不足（retrieval）还是生成过度（generation）
  - 哪类 chunk（overview/category/slide）更容易导致无证据断言

---

## 四、推荐的“组合打法”（与本仓库最贴合）

### 组合 A（默认推荐）：分层两跳 + CRAG-lite + 回归评测

- 离线：继续强化 `category_summary + overview`（你们现有默认路线）
- 在线：
  - 第一步只检索 `category_summary/overview`
  - 若证据不足（CRAG-lite evaluator 判定），再触发：改写/扩检索/补证据页
- 评测：用 Ragas 做离线回归；用 RAGChecker 做诊断

### 组合 B（“问法多样/术语不统一”的场景）：HyDE + 分层两跳

- 先 HyDE 生成 `d_hat` 做召回 → 命中类别摘要后补证据页 → 最终回答强制引用

---

## 五、把这些范式写进你们的“RAG 架构化/模板化”实施计划时，建议这样表述

- **“分层（RAPTOR 风格）”**：通过离线聚合生成 `overview/category_summary`，在线优先检索摘要层并按需补证据页，降低碎片化与上下文噪声。
- **“纠错循环（CRAG 风格）”**：引入检索质量评估器，决定是否 query rewrite / 扩检索 / 切换层级策略，提升稳定性与可控成本。
- **“自检（Self-RAG 思路）”**：将是否检索、检索目标类别、证据是否支撑的决策显式化，降低无证据回答。
- **“HyDE”**：用于 query 与语料表达差距较大时的召回增强，但最终回答必须受证据约束。

