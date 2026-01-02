# QA 问答监控与缓存设计方案

> 更新（2026-01-02）：语义缓存已在现网关闭，仅保留精确缓存（内存索引 + JSONL）。以下设计保留历史方案，若需恢复语义缓存需重新评估成本/收益。

## 1. 设计目标
- 可观测：记录用户问题、检索向量结果、LLM 应答与耗时，便于回溯与质量评估。
- 复用命中：相同或高相似问题可直接复用历史答案，减少 LLM 成本、保持一致性。
- 低侵入：在现有 `QAEngine` / `qa_cli` 基础上最小改动即可接入。
- 合规与可控：日志脱敏、可按项目名称或用户标识筛查；支持开关与采样。

## 2. 现状简述
- 问答链路：`ChromaStore.query_with_guardrails` → `QAEngine._build_prompt` → `LLMClient.generate`。
- 入口：`src/scripts/qa_cli.py`（单问单答，默认 top_k=8/top_n=5/tau=0.5）。
- 存储：检索数据保存在 `chroma_db/`；无统一的问答日志或缓存。

## 3. 总体方案
```
qa_cli / API
   ↓
Logging & Cache Middleware (新)
   ↓
QAEngine.answer
   ↓
ChromaStore + LLMClient
```
- 在 QA 调用前后插入“监控 + 缓存”中间层：负责命中检查、事件记录、落盘/持久化。
- 监控数据与缓存共享同一数据结构，支持后续分析（命中率、响应时延、准确率抽样）。

## 4. 数据模型（建议存储为 JSON lines + 可选 SQLite）
字段 | 说明
--- | ---
`question_id` | 基于规范化问题文本的哈希（如 SHA256），用于命中键。
`question_raw` | 原始用户问题文本。
`project_name` | 可选，便于分域命中。
`retrieval` | 检索输入/输出：`query_text`、`top_k`、`top_n`、`tau`、`results`（含 similarity、slide_no、project 等）。
`llm` | LLM 请求/响应：`prompt`, `answer`, `model`, `latency_ms`, `status`。
`cache_status` | `hit` / `miss` / `expired`。
`created_at` | ISO 时间戳（UTC）。
`trace_id` | 便于链路聚合，UUID。
`user_id` | 可选；默认不记录，预留字段。

## 5. 缓存策略
- **键生成**：`question_norm = normalize(question_raw)`（去空白、全角转半角、大小写/标点归一、可选中文分词去停用词），再与 `project_name` 组合哈希。
- **命中判定**：
  - 完全一致命中：同一规范化问题 + 同项目 → 直接返回缓存答案。
  - 语义近似命中（可选，二期）：对历史问题嵌入，阈值相似度 ≥0.9 时复用答案，并在监控中标记 `cache_status=semantic_hit`。
- **过期**：默认 7 天；当底层向量库有增量/重建事件时批量失效（记录向量库版本号 `vectordb_version`，不一致即失效）。
- **写入时机**：仅在 `status=success` 时写入缓存；错误只记录监控。
- **采样**：支持 `CACHE_SAMPLE_RATE`（0-1），可在配置中设置，避免全量写入导致膨胀。

## 6. 监控与日志
- **落盘位置**：`logs/qa_sessions/qa_logs_YYYYMMDD.jsonl`（新增目录）。
- **记录粒度**：一次问答一条 JSON，对应上述数据模型；包含耗时（检索耗时、LLM 耗时、总耗时）。
- **开关**：配置项 `MONITOR_ENABLED`；采样 `MONITOR_SAMPLE_RATE`；默认开启、采样 1.0。
- **隐私**：默认不记录 `user_id` 与原文上下文，可通过配置开启完整记录；敏感场景可仅存概要（similarity、slide_no），不写入 `prompt`/`answer`。

## 7. 组件改造方案
- 新增模块 `src/qa/qa_monitor.py`：
  - `class QAMonitor`: `log(event: QALog)`、`load_cache(question_id)`、`save_cache(record)`。
  - 封装文件落盘（JSONL）与简易缓存（本地 SQLite/JSONL 索引）。
- 新增配置 `config/settings.yaml`：
  - `qa.monitor_enabled`、`qa.monitor_sample_rate`、`qa.cache_enabled`、`qa.cache_ttl_days`、`qa.cache_backend`（`jsonl`/`sqlite`）。
- 调整 `QAEngine.answer`（或在外部包装一个 `QAService`）：
  1) 接收 `monitor: QAMonitor` 可选参数。
  2) 前置：根据规范化问题查询缓存，命中则返回并记录 `cache_status=hit`。
  3) 未命中则走原流程，结束后写监控记录；成功时写缓存。
- 调整 `src/scripts/qa_cli.py`：
  - 初始化 `QAMonitor`，从配置读取开关。
  - 打印命中来源（`[cache hit]`）以便人工验证。

## 8. 关键流程（伪代码）
```python
monitor = QAMonitor(cfg)
qid = monitor.build_question_id(question, project_name)
if cfg.cache_enabled:
    cached = monitor.get_cache(qid)
    if cached and not monitor.is_expired(cached):
        return cached.answer  # 记录一次命中日志

start_ts = now()
results = store.query_with_guardrails(...)
llm_answer = llm.generate(prompt_from(results))
monitor.log({
    "question_id": qid,
    "question_raw": question,
    "retrieval": results,
    "llm": llm_answer,
    "latency_ms": now()-start_ts,
    "cache_status": "miss",
})
if success: monitor.save_cache(...)
return llm_answer
```

## 9. 存储实现建议
- **首选 JSONL + 内存索引**：简单、易审计；每日滚动文件，启动时加载当日索引（question_id → last_record）。
- **可选 SQLite**：当命中需要语义近似或跨日查询时更合适；建表 `qa_logs(question_id TEXT, project_name TEXT, question_raw TEXT, answer TEXT, metadata JSON, created_at)`，加索引 `(question_id, project_name, created_at DESC)`。

## 10. 质量与安全
- **准确性**：命中返回前可附加“基于历史答案（生成时间）”提示；必要时对命中结果再做一次检索校验（抽样）。
- **一致性**：缓存与向量库版本绑定；向量库重建时提升 `vectordb_version` 以整体失效。
- **成本控制**: 统计命中率、LLM 调用次数、平均耗时，输出日/周报表（后续可加 `python -m src.scripts.qa_report ...`）。

## 11. 里程碑拆解
1) PoC：实现 `QAMonitor`（JSONL+内存缓存），QA CLI 打印命中标记，覆盖单元测试（缓存命中/过期/记录写入）。
2) 增强：支持 SQLite 后端、语义近似命中、采样配置、隐私掩码。
3) 运营化：命中/耗时指标定期汇总；向量库版本化失效；报告脚本。

## 12. 对现有代码的改动清单
- 新文件：`src/qa/qa_monitor.py`、`logs/qa_sessions/`（生成时创建）。
- 变更：`src/qa/qa_engine.py` 增加可选 monitor/caching 注入；`src/scripts/qa_cli.py` 初始化与命中提示；`config/settings.example.yaml` 添加相关配置。
- 测试：在 `tests/` 补充 `test_qa_monitor.py`（缓存/过期/日志写入）与 `test_qa_cli_cache_smoke.py`（LLM mock）。

## 13. 推荐方案（结合现有代码现状）
- 采用“两级缓存 + 监控”最小可用方案，优先落地：
  - **Level 1 精确缓存**：规范化问题（含全半角/大小写归一）+ `project_name` 作为键，命中直接返回；零向量开销。
  - **Level 2 语义缓存（写入向量库）**：复用 Chroma 新建 collection `qa_cache`; 写入项包含 `question_embedding`、`question_norm`、`answer`、`project_name`、`vectordb_version`、`answer_created_at`、`embedding_model`、`similarity_threshold_used`。命中阈值默认 0.9，TTL=7 天；命中时在回答尾部追加提示“基于历史回答，生成于 YYYY-MM-DD”。
  - **监控**：沿用本方案第 6 章 JSONL 记录，增加字段 `cache_level`（none/exact/semantic）、`semantic_score`。
- 为什么推荐：
  - 复用现有 Chroma/embedding，无新增基础设施，改动集中在 QA 层。
  - 高阈值 + TTL + `vectordb_version` 绑定，降低误命中风险；通过命中提示增加可解释性。
  - 交付快：PoC 可在 1 个迭代完成，后续再加自适应阈值或抽样复核。

## 14. 语义缓存写入与命中流程细化
1) **写入时机**：`status=success` 后，将问题 embedding 与答案写入 `qa_cache` collection；同时写 JSONL 监控。
2) **命中顺序**：先查精确缓存 → 不命中再向量检索 `qa_cache`，返回最高相似项；若相似度 ≥ `semantic_threshold` 且未过期 → 命中。
3) **失效策略**：
   - 时间：`cache_ttl_days`（默认 7）。
   - 版本：记录 `vectordb_version`，当底层知识库重建或增量时提升版本，使旧缓存失效。
   - 容量：可选 LRU/命中频次清理（后续迭代）。
4) **风险防控**：
   - 命中回答附生成日期；可配置“复核模式”在命中后再跑轻量检索校验（抽样）。
   - 记录 `semantic_score` 以便误命中分析；定期统计命中率/误命中率。
5) **配置新增**（示例键）：
   - `qa.cache_enabled`（bool）
   - `qa.cache_semantic_enabled`（bool，默认 true）
   - `qa.cache_semantic_threshold`（float，默认 0.9）
   - `qa.cache_ttl_days`（int，默认 7）
   - `qa.vectordb_version`（string/int）
   - `qa.cache_collection`（string，默认 `qa_cache`）

## 15. 后续增强路径
- 自适应阈值：按问题不确定性/长度动态调节阈值，参考 VectorQ 动态阈值思路。
- 语义近似复核：命中后对当下文档再做 top-1 检索比对，低成本验证答案一致性。
- 指标与报告：新增脚本汇总命中率、平均延迟、误命中率，供运营调参。

## 16. 调试友好的端到端监控（输入/输出捕获）
- **记录范围**：对每次调用完整保存输入和输出，便于回溯：
  - 输入：用户原始问题、规范化问题、项目名、top_k/top_n/tau、cache 配置、向量库版本。
  - 检索输出：召回条目（metadata、similarity、slide_no）、截断后的 context 片段（可配置是否全量保存）。
  - LLM 输入/输出：最终 prompt（可开启“脱敏/摘要模式”仅记录模板占位与长度）、生成答案、模型名、LLM latency。
  - 缓存状态：命中层级（exact/semantic）、命中分数、TTL 剩余时间、是否复核通过。
  - 结果汇总：总耗时、状态码、trace_id、question_id。
- **存储与结构**：
  - JSONL 仍为主通道，新增 `debug` 节点，用于放大字段（如完整 prompt/context）；可通过 `qa.monitor_debug_mode` 控制是否写入。
  - 在 `logs/qa_sessions/` 按日滚动；当 `monitor_debug_mode=true` 时文件名追加后缀 `-debug`，便于区分与定向清理。
- **采样与开关**：
  - `qa.monitor_enabled`：全局开关。
  - `qa.monitor_sample_rate`：总体采样；`qa.monitor_debug_rate`：仅对 debug 字段的额外采样，默认 0（不开）；支持按 `question_regex` 白名单提升采样。
  - CLI 参数覆盖：`--monitor-debug` 可临时启用全量记录，便于现场调试。
- **隐私与安全**：
  - 默认 debug 关闭，避免记录敏感原文；开启时可选“摘要模式”仅保存前 N 字与 SHA256 指纹。
  - 清理策略：debug 文件保留期可短于常规日志（如 3 天），配置 `qa.monitor_debug_retention_days`。
- **调试辅助脚本**（后续可添加）：`python -m src.scripts.qa_trace_viewer --trace-id <id>` 读取对应 JSONL 条目，打印输入/输出/命中链路。

## 17. 策略模式落地建议（监控与缓存可插拔）
- **监控三类策略接口**：
  - `ILogSink`：写出渠道（JSONL、SQLite、OTel/HTTP 等）。示例：`JsonlSink`, `SqliteSink`, `OtelSink`。
  - `ISampler`：采样与粒度判定（normal/debug/skip）。示例：`FixedRateSampler(p)`, `RegexBoostSampler(patterns, base, boost)`, `DebugOnFlagSampler(flag)`。
  - `IRedactor`：脱敏/摘要。示例：`TruncateRedactor(n)`, `HashRedactor(fields=[prompt,context])`, `PassThroughRedactor`。
- **QAMonitor 组合而非继承**：
  - 构造签名：`QAMonitor(sinks: list[ILogSink], sampler: ISampler, redactor: IRedactor)`。
  - 流程：`decision = sampler.pick(event)` → `sanitized = redactor.apply(event, level=decision.level)` → `sink.write(sanitized)`（可多 sink）。
- **缓存策略接口**：
  - `ICacheLookup`：`ExactMatchLookup`、`SemanticLookup(threshold)`、`HybridLookup(order=["exact","semantic"])`。
  - `ICacheEvictor`：`TtlEvictor(days)`、`VersionEvictor(vectordb_version)`、`LruEvictor(capacity)`。
- **目录与配置建议**：
  - 代码：`src/qa/monitoring/` 下拆分 `sinks.py`, `samplers.py`, `redactors.py`, `cache_strategies.py`，`qa_monitor.py` 作为门面。
  - 配置：`config/settings.yaml` 增加 `qa.monitor.sink`, `qa.monitor.sample_rate`, `qa.monitor.debug_rate`, `qa.monitor.redactor`, `qa.cache.strategy`, `qa.cache.semantic_threshold`。
- **默认实现（PoC 即可用）**：
  - `JsonlSink` + `FixedRateSampler(p=1.0)` + `TruncateRedactor(n=300)` + `HybridLookup(exact→semantic, threshold=0.9, ttl=7d, vectordb_version bound)`。

## 18. 规范与文档同步要求
- 参考根目录 `AGENTS.md`（仓库通用规范）与 `CLAUDE.md`（工具/Agent 说明）约定进行同步更新：
  - 按 `AGENTS.md` 的文档与命名规范，补充监控/缓存能力、配置键、默认阈值/TTL/日志路径、采样与脱敏默认策略。
  - 按 `CLAUDE.md` 的使用说明格式，记录新增命令或入口（如 `--monitor-debug`, `qa_trace_viewer`）、策略组件清单，以及与其他工具/agent 的协作关系。
- 新增文件/目录（如 `logs/qa_sessions/`, `src/qa/monitoring/`）需在上述文档中被引用，便于维护和审计。
