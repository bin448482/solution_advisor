# QA 问答监控与缓存测试方案

## 1. 目的与范围
- 覆盖 QA 链路的监控与缓存改造，确保命中逻辑、日志完整性与安全配置按设计方案落地。
- 验证 CLI (`python -m src.scripts.qa_cli ...`) 在开启/关闭监控与缓存时的行为差异。
- 适用于本地 PoC 与 CI 烟囱测试，默认使用 LLM mock 与最小样例 PPT。

## 2. 前置条件
- 环境：Python 3.10+，已安装 `requirements.txt`；可访问 `chroma_db/`；可写 `logs/qa_sessions/`。
- 配置：基于 `config/settings.example.yaml` 生成实际配置，关注键 `qa.monitor_enabled`、`qa.monitor_sample_rate`、`qa.cache_enabled`、`qa.cache_ttl_days`、`qa.cache_semantic_enabled`、`qa.cache_semantic_threshold`、`qa.vectordb_version`。
- 数据：准备一个小型 PPT 输入，确保向量库已构建；LLM 使用 `LLM_PROVIDER=mock`。

## 3. 测试项与用例要点
### 3.1 缓存准确性（精确键）
- 首次提问命中状态应为 miss，写入缓存与监控日志。
- 同一规范化问题 + 同项目在 TTL 内应 `cache_status=hit`，返回缓存答案且不触发 LLM；日志追加命中记录。
- TTL 过期后再次提问应重新调用检索与 LLM，`cache_status=expired`。
- `vectordb_version` 变更后缓存应整体失效，命中率归零。

### 3.2 语义缓存（可选）
- 开启 `qa.cache_semantic_enabled=true` 且阈值 0.9：相似表述应记录 `cache_status=semantic_hit`，附带 `semantic_score`。
- 阈值调低至 0.7 时验证误命中风险：低相关问题不应命中；必要时再走检索。

### 3.3 监控日志完整性
- `logs/qa_sessions/qa_logs_YYYYMMDD.jsonl` 每次问答一条，包含 question_id、retrieval、llm、cache_status、latency_ms、trace_id。
- 开启 `qa.monitor_debug_mode` 时应追加 debug 文件后缀 `-debug`，并包含 prompt/context 摘要或脱敏结果。
- 采样：`qa.monitor_sample_rate=0.5` 时重复 10 次提问，日志数量约为 50%（允许浮动）。

### 3.4 CLI 交互与输出
- 命中缓存时 CLI 输出前缀 `[cache hit]` 或 `[semantic hit]`，并返回缓存答案。
- 关闭缓存 `qa.cache_enabled=false` 时，所有请求均为 miss，日志仍记录。
- CLI 参数覆盖配置：`--monitor-debug` 开启后应写入 debug 字段；关闭配置不受影响。

### 3.5 错误与降级
- LLM 调用异常时：返回错误提示，日志记录 `status=error`，不写缓存。
- 日志目录不可写时：CLI 不应崩溃，给出可读错误并跳过监控（降级）。
- 缓存文件损坏/缺失：应自动重建或忽略损坏条目，流程继续。

### 3.6 性能与成本
- 同一问题连续 5 次：开启缓存总耗时应显著低于关闭缓存（至少减少 LLM 调用耗时部分）。
- 日志写入开销：在 mock 模式下单次问答总耗时 < 1s 为可接受基线。

## 4. 测试步骤建议
1) 构建向量库（如需）：`python -m src --input ppts/<sample>.pptx --output ppt_outputs/<sample> --force`。
2) 运行 CLI 基线：`python -m src.scripts.qa_cli -q "样例问题" --config config/settings.yaml`，确认 miss 与日志生成。
3) 重复同问，验证 cache hit；修改配置测试语义缓存与阈值。
4) 切换 `qa.monitor_sample_rate` 与 `qa.monitor_debug_mode`，比对日志文件数量与内容。
5) 模拟故障：手动锁定日志目录或破坏缓存文件，观察降级表现。

## 5. 验收标准
- 命中/过期/失效场景均按设计状态返回且日志准确。
- 配置开关与 CLI 覆盖参数生效，无未记录或误记录字段。
- 故障场景不中断问答主流程，且有清晰提示。
- 性能基线满足预期，未出现明显抖动或阻塞。