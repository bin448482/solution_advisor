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
