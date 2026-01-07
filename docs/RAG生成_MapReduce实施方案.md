# RAG 自动生成（模拟人工版）Map-Reduce 实施方案

## 背景与目标
- 现状：默认关闭自动 RAGPrep，人工按 `docs/generate_rag_documents.md` 产出高质量 `rag_documents.json`。
- 诉求：在自动链路中尽量复刻人工质量，尤其是长文档时的“全局聚合+严格格式”。
- 目标：实现分层 Map-Reduce 流程，生成以 `category_summary` 为主的 `rag_documents.json`，控制上下文长度、减少碎片化，同时保留人工兜底能力。

## 适用范围
- `auto_ragprep_enabled=true` 时启用此方案；默认仍为人工模式。
- 输入：`ppt_outputs/<project>/page_summaries/*.json`（单页摘要）。
- 输出：`ppt_outputs/<project>/embeddings/rag_documents.json`，主要包含 `category_summary` + `overview`，可选保留 `qa_pair`。

## 现有自动版的痛点
- 全量输入易超上下文，导致截断/遗漏。
- 以单页 QA 为主，碎片化、重复、噪声难控。
- 分类漂移、幻觉难以肉眼发现。

## 设计概览（分层 Map-Reduce）
- Map：按批（8–12 页）处理，输出局部类别候选 + 100–150 字摘要 + 1–2 QA。
- Shuffle/合并：收集所有候选类别，按名称/语义合并为 6–12 个全局类别。
- Reduce：对每个全局类别汇总跨批 slide，生成 200–300 字 `category_summary` + 3–5 QA，附 `source_slide_refs`、`source_files`。
- Overview：基于所有类别摘要生成 1 条项目级 `overview` chunk。

## LangGraph 实现（取代旧自动 QA/chunk 分支）
- 目标：彻底替换旧版 QA → 分类 → 多 chunk 的自动分支；`auto_ragprep_enabled=false` 仍为默认，人工优先不变。开启自动时，直接走 LangGraph Map/Reduce，产物仅 `category_summary` + `overview`。
- 拆分节点：`load_batch`（读取批次 slide 摘要）→ `map_categories`（LLM 生成批次类别与摘要/QA）→ `merge_categories`（LLM 或向量合并全局类别）→ `reduce_category`（LLM 汇总类别）→ `build_overview`（LLM 输出 overview）→ `validate_emit`（结构校验 + 落盘）。
- 编排方式：采用 LangGraph `StateGraph`，状态字段含 `batches`、`map_results`、`global_categories`、`reduce_results`、`overview`、`errors`。`map_categories` 并行处理每批；`reduce_category` 并行处理全局类别。
- 伪代码（核心节点），放在 `src/rag/map_reduce_graph.py`：
```python
from langgraph.graph import StateGraph, END

def map_categories(state):
    # 输入: state["current_batch"]
    # 输出: append 批次 map 结果
    return {"map_results": state["map_results"] + [llm_map(state["current_batch"])]}

def merge_categories(state):
    merged = merge_with_llm_or_vectors(state["map_results"])
    return {"global_categories": merged}

def reduce_category(state):
    cat = state["current_category"]
    return {"reduce_results": state["reduce_results"] + [llm_reduce(cat)]}

def build_overview(state):
    return {"overview": llm_overview(state["reduce_results"])}

def validate_emit(state):
    validate_schema(state["reduce_results"], state["overview"])
    persist(state, out_path)
    return { "done": True }

builder = StateGraph(dict)
builder.add_node("map", map_categories)
builder.add_node("merge", merge_categories)
builder.add_node("reduce", reduce_category)
builder.add_node("overview", build_overview)
builder.add_node("validate_emit", validate_emit)

builder.add_edge("map", "merge")
builder.add_edge("merge", "reduce")
builder.add_edge("reduce", "overview")
builder.add_edge("overview", "validate_emit")
builder.set_entry_point("map")
builder.set_finish_point("validate_emit")
graph = builder.compile(parallel_edges=[("map", "merge"), ("merge", "reduce")])
```
- 配置建议（`config.Settings` 复用/新增字段，沿用 `auto_ragprep_enabled` 作为总开关）：
  - `map_batch_size`、`map_max_categories_per_batch`、`reduce_target_categories`、`map_temperature`/`reduce_temperature`。
  - `langgraph_max_concurrency` 控制并行 map/reduce；默认 4~8。
  - `llm_provider`/`model` 与现有 `LLMClient` 保持一致，便于复用缓存/监控。
- Prompt 要点：
  - Map：严格要求输出 JSON、每类 100–150 字摘要、可选 1–2 QA；附 `source_slide_refs`。
  - Merge：给出候选类别列表，要求重命名并合并相似项（>0.8），输出 6–12 个全局类别及对应 slide_refs。
  - Reduce：每类 200–300 字 `category_summary` + 3–5 QA，答案 ≤ 200 字，必须引用 slide_no。
  - Overview：150–200 字，涵盖定位/价值/亮点/风险。
- 校验与重试：`validate_emit` 节点可对 JSON 结构、长度、引用合法性做校验；若失败，记录 `errors` 并可选触发单节点重试（LangGraph 自带）。
- 落地位置：新增 `src/rag/map_reduce_graph.py` + 对应 `AGENTS.md`；在 `pipeline.py` 的 RAGPrepStage 中，当 `auto_ragprep_enabled=true` 时直接调用 LangGraph（旧 QA/chunk 自动分支将被移除）。

## Map 层细节
- 输入：当前批次的 `page_summaries` 精简字段（`slide_no`、`title/one_liner`、关键 bullets、entities）。
- 批大小：推荐 8–12 页；根据 token 决定。
- 模型设置：`temperature=0~0.2`，禁止编造，语言与原文一致（通常中文）。
- 输出 JSON 示例：
```json
{
  "batch_id": "batch_01",
  "categories": [
    {
      "category_name": "核心功能",
      "category_hint": "features/core",
      "slides": [3,4,5],
      "summary": "100-150字摘要",
      "qa": [
        {"q": "...", "a": "...<=120字...", "source_slide_refs": [3,5]}
      ]
    }
  ]
}
```
- 约束：每批 3–6 个类别，QA 可选但不超过 2 条/类。

## Shuffle / 合并规则
- 同名直接合并；相似度 > 0.8（可用向量或 LLM 判定）合并并统一命名。
- 目标全局类别数：6–12 个，避免过细。
- 保留合并映射，记录每类涉及的 slide_no、source_files。
- `category_id` 规范：全局类别在 Reduce 阶段必须生成稳定的 `category_id`，取 `category_name` 做语义化 slug（保留中英文，其他符号替换为 `_`，转小写，必要时追加序号去重）。禁止使用空值或无意义占位符（如 `agent`），应能反映类别含义，例如 “产品定位”→`产品定位` 或 `product_positioning`。生成失败时需 fallback 为 hash，但仍应保持唯一。

## Reduce 层细节
- 输入：某全局类别下的所有 slide 摘要 + Map 层局部摘要/QA。
- 模型提示要点：
  - 生成 1 条 `category_summary`，摘要 200–300 字，覆盖能力/场景/价值/限制（如有）。
  - 生成 3–5 QA，答案 ≤ 200 字；`source_slide_refs` 去重升序。
  - 禁止编造 PPT 未出现的信息；必须可追溯。
- 输出结构（与人工版一致）：`chunk_type=category_summary`，含 `text`、`metadata.summary`、`metadata.qa_examples`、`source_slide_refs`、`source_files`。

## Overview 生成
- 输入：所有 `category_summary` 的摘要片段。
- 输出：1 条 `overview` chunk，简述产品定位、核心价值、目标用户、亮点/风险，150–200 字。

## 长度控制与去噪
- Map：仅取关键字段，丢弃冗长 details；必要时截断 bullets 数量（如前 8 条）。
- Reduce：若类别仍超长，可再对该类别做二级 Map-Reduce（少用）。
- 对低置信 slide 可降权或排除（需保存决策供审计）。

## 校验与自检
- 结构：JSON 可解析；字段齐全；chunk_type 合法。
- 长度：summary 200–300 字；QA 答案 ≤ 200 字。
- 引用：`source_slide_refs` 必须存在于 `page_summaries`；`source_files` 指向实际文件。
- 唯一性：每个类别仅 1 条 `category_summary`。
- 抽检：随机抽 1–2 类做“对照检查”提示，确认无编造与关键遗漏。

## 配置与开关
- `Settings.auto_ragprep_enabled=true` 时启用自动版；默认 false。
- 可增加 `map_batch_size`、`max_categories` 等设置（若落地代码需新增字段）。
- 依赖约束：`requirements.txt` 已固定 `langchain==0.1.20`、`langgraph==0.1.13` 及对应 provider 版本，保持 API 兼容。

## 建议落地步骤
1) 在 `RAGPrepStage` 内新增 `MapReduceCategoryBuilder`（map/merge/reduce 方法），调用 `LLMClient`。
2) 先只产出 `category_summary` + `overview`，暂不生成 per-slide `qa_pair/topic/step/metrics`，避免碎片化。
3) 生成后运行校验脚本（结构/长度/引用），失败则标记为 auto-draft 并提示人工复核。
4) 保留人工模式作为准生产路径；自动模式定位为草稿/批处理，可人工抽检后再入库。

## 风险与缓解
- 幻觉/编造：低温度 + 强约束提示 + 抽检。
- 分类漂移：限制类别上限并做相似度合并；保留人工更名口径。
- Token 过长：批切分 + 精简字段；必要时换长上下文模型。
- 成本：Map 与 Reduce 各一次/批与/类，整体调用量可控；可并行但注意并发上限。

## 发现的设计缺陷与补充要点
- 固定分类口径：Map/Merge 阶段仅接受 8 个标准类别（positioning、features、architecture、integration、cases、comparison、deployment、roadmap），未命中标准类别的候选直接丢弃，不再生成“其他信息”等兜底类；slug = 标准 category_id。
- 结构与长度校验：Validate 节点必须校验 summary 200–300 字、qa 3–5 条且答案 ≤200 字、source_slide_refs 非空且去重、chunk_type 合法；失败应重试或记录 error，禁止直接落盘。
- 文本格式规范：统一 text 拼装模板（含项目名、【Category】、【Summary】、【Representative Q&A】与“来源页 [x]”），original_json 至少保留 source_files、qa_count 以便审计。
- 合并策略强化：Merge 需加入语义/向量相似度合并与阈值，避免仅按字符串；“其他信息”类别应有触发阈值和清晰命名，防止强行兜底混杂。
- 溯源与审计：保留 map_summaries、合并映射、生成/解析错误到日志或 metadata，便于对照人工稿。
- Overview 约定：明确是否必产 overview，若产出需给出长度与字段要求；如不需要，应在 emit 前过滤，保持与人工稿一致。
- Fallback 收敛：map 解析失败的 fallback 结果不应直接写入正式 rag_documents，应标注低置信或触发重试，防止污染类别摘要。
- Prompt 补强：Map 提示显式列出 8 个标准类别（含中英文），只能从列表选择且“无法归类则跳过”；Map 仅输出 category_name/category_hint/slides，不生成 summary/QA（由 Reduce 阶段负责）。Reduce 提示才生成 200–300 字摘要与 3–5 QA。
- QA 引用缺失处理：不强行编造 source_slide_refs；如 QA 无引用则保留内容并在 metadata 标记 qa_missing_refs=true，便于后续人工补全。
