# RAG 优化：LLM 预处理分类实施计划

**日期**：2026-01-02  
**适用项目**：`ChatBI产品介绍_2025` 及后续同类 PPT 项  
**输入来源**：`ppt_outputs/<项目>/page_summaries/*.json`（现有 PageSummary）  
**目标产出**：`ppt_outputs/<项目>/embeddings/rag_documents.json`（含分类元数据），并入向量库（Chroma）

---

## 1. 现状摘要
- 之前按“每页 1 个 chunk”入库，粒度粗、主题混杂，纯向量检索噪声多。
- 目标转向：**预编排问答 + 相似度匹配**，不强依赖在线分类。通过预先整理高价值问题及答案，降低噪声、提升命中。

## 2. 方案概览（预编排 QA 优先）
在知识沉淀阶段，先基于 PageSummary / 项目画像编排“核心问答清单”，再入库：
1) **QA 对块为主**：每个高价值问题生成 1 个答案块；同一主题列出 5–10 个多样化问法。  
2) **主题块/步骤/指标** 可选补充，用于长文回答或复杂流程，但不必按页全量存。  
3) 项目 overview 保留少量全局语境。

## 3. 分类/标签（可选）
- 若需要主题标签，用固定映射表（ID + 中文名）而非在线分类；过滤可选用 `_id` 字段。  
- 但核心检索依赖“问句相似度”而非分类过滤，分类只作轻量辅助。

## 4. Chunk 设计（以 QA 为主）
| chunk_type | 粒度 | 组成 | 适用场景 |
| --- | --- | --- | --- |
| qa_pair (主) | 80~150 词 | 预编排问法（多样化）+ 精炼答案；1 问 1 答 | 主力检索，低噪声 |
| topic (辅) | 150~300 词 | 同一主题的 bullets+details 语义分段，含 title_hint | 长文补充/引用 |
| step (可选) | 80~150 词 | 流程/步骤拆分；step_no, step_group | “如何做/流程”问法 |
| metrics (可选) | 80~150 词 | 指标/表格摘要，含数字项 | 数值型问答 |
| overview | 200~300 词 | 项目画像，slide_no=0 | 全局语境、冷启动 |

## 5. 元数据规范
- 基础：`project_name`, `chunk_type`, `source_slide_refs`（列表，可为空）, `level`。  
- 标签（可选）：`category_id`（固定表，如 integration）、`category_name`（中文可读）；多标签用 `|` 串。  
- QA 专属：`qa_question`（主问法），`alt_questions`（`|` 串，同义问法），`answer` 存在 `text` 字段。  
- 追溯：`indexed_at`、`original_json`。

## 6. 处理流程（QA 优先）
1) 读取 PageSummary / 项目画像，人工或 LLM 辅助列出核心问题清单（多问法）。  
2) 为每个问题生成精炼答案（可用 LLM 基于 PageSummary/原文组装，人工校对）。  
3) 形成 `qa_pair` chunk：`qa_question`+`alt_questions`+`answer`，附 `category_id/name`（可选）与 `source_slide_refs`。  
4) 选做：对剩余长文生成 topic / step / metrics 块补充。  
5) 写出 `embeddings/rag_documents.json`，序列化多值字段为字符串。  
6) 入库：`vectordb_cli import-docs`。  
7) 验证：块数、问法覆盖度、导入 0 失败；冒烟查询（纯相似度检索问句）。

## 7. 评估计划
- 数据：抽样 ≥100 slides 标注真值（分类 + 相关性）。  
- 指标：P@5 / R@10（有/无分类过滤对比）；未分类率；分类一致性（kappa）。  
- 实验：A/B 检索（A=仅向量，B=分类过滤+向量），记录命中率差异。

## 8. 检索使用示例（无分类也可命中）
- 问句：“用户可以通过哪些入口提问（Web、移动、钉钉/企业微信、内嵌组件）？”  
  - 直接向量检索：对比 `qa_question`/`alt_questions` 做相似度；返回的 qa_pair 应在答案中明确列出 Web/移动/钉钉/企微/内嵌/SDK/IM 等。  
  - 若启用轻量标签过滤：`where={"category_id": {"$contains": "integration"}}`（可选，非必需）。  
- 低置信回退：若 top1 相似度 < 阈值（如 0.5），提示改写或返回 top_k 供选择。

## 9. 发布与回滚
- 增加特性开关：`ENABLE_LLM_CLASSIFY`、`ENABLE_TOPIC_CHUNKS`（默认关）。  
- 双写期：生成新 rag_documents + 入库，但检索侧先按旧逻辑；验证后再放量开启分类过滤。  
- 回滚：关闭开关、保留旧向量，或清理新 collection。

## 10. 成本与性能
- 规则分类零成本；LLM 终判：每页约 400–600 tokens，40 页≈2.4 万 tokens；选 GPT-4o-mini/Haiku，批量 8–10 页。  
- QA 生成：每主题 2–3 Q&A，控制总 tokens，必要时只对高价值主题生成。  
- 并发 3–5；新增耗时 < 2s/页为目标。

## 11. 后续迭代
- 置信度字段（LLM 返回 score）；  
- 分类导航/分布统计；  
- 主题聚类与知识图谱探索；  
- 与 `page_type` 统一映射表，定期清洗旧库。

## 12. 操作清单（MVP）
1) 实现分类与重切分脚本/模块（可复用 `src/rag.py` 新增分类函数）。  
2) 生成新的 `rag_documents.json`。  
3) 更新 manifest 中 `rag_documents` 计数。  
4) `vectordb_cli import-docs` 重建 Chroma。  
5) 冒烟查询 + 抽样质检。  
6) 记录实验结果，决定是否启用分类过滤。

## 13. QA 问答缓存衔接（2026-01-02 更新）
- 缓存仅保留“精确匹配”两级：内存索引（启动时加载 `logs/qa_sessions/qa_cache.jsonl`）+ JSONL 持久化，键为 `normalize(question)+project_name+vectordb_version`。  
- 语义相似度缓存/向量匹配已关闭；未命中时直接走项目内向量检索，不再对历史问题做向量相似度比对。  
- 现网配置：`qa.cache.cache_semantic_enabled=false`，命中返回 `cache_level=exact`，便于问题复用且避免多余的向量查询。

---

**状态**：实施计划（可立即执行）  
**待决策**：是否使用 LLM 分类（成本 vs 质量），是否开启检索侧分类过滤。

---

**2026-01-02 实施同步**  
- 已落地特性开关：`enable_llm_classify`、`enable_topic_chunks`、`enable_step_chunks`、`enable_metrics_chunks`（配置默认关闭）。  
- refine 流程与主线保持一致，统一生成 QA/Topic/Step/Metrics/Overview chunk。  
- 元数据增加 `source_slide_refs`，所有 list 元数据入库前统一序列化为 JSON 字符串，便于追溯与过滤。  
- mock LLM（测试）下提供确定性 QA 生成，避免 JSON 解析失败导致 rag 文档缺失。
