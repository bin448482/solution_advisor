# PPT解析与RAG重构实施方案

## 背景与问题
- 现行流程：`PPT -> 图片/文本 -> 多模态摘要 -> 项目画像 -> RAG文档 -> 向量库 -> QA`。
- 痛点：渲染/截图稳定，但多模态 LLM 解读波动大；低置信页需要多轮 refine；重跑会重复耗时阶段。

## 重构目标
- 把“确定性采集”（渲染/提取）与“概率性理解”（LLM 汇总/重排）彻底解耦，可独立重跑。
- 提供面向任务的封装：`ingest()`（写入向量库）、`answer()`（检索+重写）、`refine()`（按规则重跑摘要）。
- 支持增量/幂等：同一 PPT、同一 slide 只要原始文件未变，采集缓存复用；refine 只触发 LLM 阶段。

## 目标架构（两段式）
1) **Ingest Pipeline（数据采集→向量库）**
   - Stage0: `FileHash` & manifest 初始化（记录输入哈希、配置版本）。
   - Stage1: `Capture` 渲染/截图（LibreOffice + pdftoppm），输出 `slides/*.png`。
   - Stage2: `Extract` 结构化文本（python-pptx），输出 `slide_texts.jsonl`。
   - Stage3: `Interpret` 多模态摘要（LLM，支持 batch/并行），输出 `page_summaries/*.json` + 置信度。
   - Stage4: `Profile` 项目画像汇总。
   - Stage5: `RAGPrep` 清洗、拆分、组包，生成 `embeddings/rag_documents.json`。
   - Stage6: `VectorSink` 写 Chroma（可开关）；记录 `vectordb_metrics`。
2) **QA Pipeline（问题→检索→重写）**
   - `Retriever`（ChromaStore.query_with_guardrails）+ `AnswerComposer`（LLM）。
   - 元数据过滤：项目/页类型；缺失时返回“未找到”而非空答。

## 核心封装与改造点
- **Pipeline Orchestrator**：`PipelineRunner` 接收 `stages` 列表（策略模式），统一上下文对象 `{pptx_path, output_dir, settings, manifest}`，支持跳过已完成 Stage。
- **Stage Contract**：`Stage.run(ctx) -> StageResult`，写入 ctx.manifest，标记 slide-level 状态（captured/extracted/summarized/refined）。
- **Refine Engine**：
  - 入口：`PPTPipeline.refine(threshold|page_type|explicit_list)`。
  - 只重跑 Stage3-Stage5，重用 Stage1/2 产物；保持 slide deterministic 输入。
  - 增加 `refine_log.jsonl` 记录每次重跑的原因、旧置信度、新置信度、模型版本。
- **Cache 与幂等**：
  - 以 `file_hash` + `slide_no` + `model_version` 作为摘要缓存键。
  - 允许 `--force-capture`（清空 Stage0-2）与 `--force-interpret`（重跑 Stage3-5）。
- **Observability**：
  - manifest 增加 `stages` 段：每个 Stage 的开始/结束时间、成功/失败计数。
  - slide 层错误写入 `errors[]`，同时写 `page_summaries/<id>.json` 的 `issues` 字段。

## 针对 LLM 波动的设计
- **稳定输入**：摘要输入由三部分组成：`image_path`（固定）、`extracted_text`（固定）、`page_context`（上一页/目录信息可选），保证重跑一致。
- **质量阈值**：置信度 < `refine_threshold`、或检测到 JSON 噪声、或关键信息缺失（如 page_type 未识别）时自动进入 refine 队列。
- **模型切换策略**：refine 阶段可指定更高质量/不同提供商模型；manifest 记录 `llm_provider`、`llm_model` per run。
- **人机校验插槽**：预留 `manual_override/` 目录，可放置手工修订的 `page_summaries`，Pipeline 自动优先使用。

## 向量库集成调整
- 写入前统一去重：`id = <project>_<slide_no|overview>`；插入前 `delete where source==project`（可配置）。
- Batch 大小、并行度从 Settings 读取；失败项返回列表，写 manifest。
- 允许 `--no-vectordb` 跳过写库，只生成 embeddings 供离线检查。

## 实施路线图（建议三迭代）
1) **迭代1：结构拆分与缓存**
   - 引入 `PipelineRunner` + Stage 抽象，拆出 Capture/Extract/Interpret/Profile/RAGPrep/VectorSink。
   - manifest/stage 结构调整；保留现有 CLI 入口，参数新增 `--force-capture/--force-interpret/--no-vectordb`。
2) **迭代2：Refine & 观测性**
   - 完成 refine 队列与阈值驱动；新增 `refine_log.jsonl`。
   - 补充 slide-level issue 标记、stage 计时与错误聚合。
3) **迭代3：QA 合规与体验**
   - Retriever 统一 metadata 过滤；缺省返回“无相关内容”。
   - AnswerComposer 模板化（可换模型）；加引用格式统一。

## 交付物与验收
- 代码：`src/pipeline_runner.py` + Stage 类；`PPTPipeline` 重写为 orchestrator 配置。
- 文档：本实施方案，更新 `AGENTS.md/CLAUDE.md` 的命名规范，README 新增运行示例。
- 测试：保留 e2e smoke，新增 refine 场景（低置信 → 提升）与向量库去重测试。

## 风险与缓解
- LibreOffice 依赖不可用 → Stage1 提供前置检查与友好报错。
- LLM 成本/限流 → 支持按 slide 范围运行、并发可配置、模型分级。
- 兼容性 → 保留旧 CLI 参数映射，增加 deprecation 警告。
