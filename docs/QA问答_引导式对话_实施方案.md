# QA 问答引导式对话实施方案

## 1. 背景与目标
- 现状：CLI/QA 引擎为单轮问答，未命中直接提示“文档未提及”，缺少对用户的引导与信息收集。
- 目标：在不破坏现有检索与答案质量的前提下，引入“澄清-检索-引导”多轮模式，提升命中率、体验与数据收集效率。
- 成功指标（首轮上线版）：
  - 命中率提升 ≥10%（以有效回答率计算）。
  - “无结果”占比降低 ≥30%。
  - 用户补充信息率 ≥50%（在首轮澄清后提供至少 1 个槽位值）。

## 2. 设计原则
- 最小侵入：不重写 QAEngine 流程，新增对话编排层包装原有接口。
- 可配置：槽位、引导文案、推荐问题模板通过 YAML/JSON 配置。
- 可回退：保留现有单问单答模式，配置开关一键关闭引导。
- 可观测：沿用监控/缓存日志结构，追加引导阶段事件。

## 3. 总体方案
```
用户输入
  ↓（复述 + 槽位澄清 + 推荐问题）
Dialogue Orchestrator（新）
  ↓（填充槽位 → 查询参数）
QAEngine.answer（原） + ChromaStore + LLM
  ↓
回答 + 下一步引导选项（按钮式文案/CLI 文本）
```
- 新增 **Dialogue Orchestrator**：维护对话状态、槽位、推荐问题生成，封装检索调用。
- 未命中或低置信时走“信息缺口提示”分支，返回可选追问；命中后附“下一步”推荐。

## 4. 对话流程（状态机）
1) `clarify`：首轮复述问题，返回 3–5 个可选槽位（项目名/阶段/模块/对象/时间线），用户可选或直接继续。
2) `fill_slots`：收集槽位后构造查询上下文（拼接到检索 query 与 metadata 过滤）。
3) `retrieve_answer`：调用 `QAEngine.answer`；若命中低于阈值或结果为空，进入 `gap_prompt`。
4) `gap_prompt`：给出 2–3 个引导问题/选项，引导用户补充；若仍失败，提供“提交补充资料”与“查看常见问题”。
5) `follow_up`：每次回答后推送 2–3 条“下一步”引导（可点选生成新问题）。

## 5. 槽位与模板（配置驱动）
- 槽位示例（默认启用）：`project_name`、`phase`（立项/实施/收尾）、`module`（范围/里程碑/风险/资源/预算/联系人）、`timeframe`。
- 推荐问题模板（按模块）：
  - 概览：项目目标、关键交付物、成功指标。
  - 时间线：里程碑、关键依赖、延误风险。
  - 角色：负责人/干系人、联系人方式。
  - 资源与预算：人力、工具、预算上限/审批。
  - 风险与缓解：当前 top-3 风险、缓解动作、触发条件。
- 文案示例：
  - 澄清提示：“我理解您想问『{question}』。为了更准确回答，可补充：项目名/阶段/关注模块？直接回复序号即可（如 1,3）。”
  - 无结果提示：“暂未找到预算细节。要不要先看 ①项目目标 ②里程碑 ③团队构成？或补充项目名/阶段。”

## 6. 组件改造清单
- 新增：`src/qa/dialogue_orchestrator.py`
  - 维护 `DialogueState`（槽位、最近命中、历史问题）。
  - `build_clarify_message(question)` 返回澄清文案 + 可选项。
  - `enrich_query(question, slots)` 生成检索 query/filters。
  - `next_suggestions(context)` 基于命中模块推送后续引导。
- Orchestrator 默认使用 LLM（可退化为纯模板）：
  - clarify：LLM 复述问题 + 产出候选槽位值（受控列表内）。
  - apply_slot_selection：LLM 将用户自由文本映射到受控槽位；输出 JSON，超出词表置空。
  - follow_up / gap_prompt：LLM 生成 2–3 条追问或下一步选项，长度裁剪；解析失败回退模板。
  - 语境保持：传入最近 1–2 轮的问题、已填槽位与已回答模块，要求 LLM 避免重复追问；对重复问题输出“已回答/是否需更新槽位”提示。
  - 去重与冷却：对推荐问题/追问做去重，且同一模块的推荐在 2 轮内不重复（可在 state 存储最近推荐集，LLM 提示中附带 `recent_suggestions`）。
  - 槽位去重：已填槽位不再出现在后续澄清/追问候选；LLM 接口入参需附 `filled_slots`，提示“不要再次请求这些槽位”。
- 扩展：`src/scripts/qa_cli.py`
  - 增加 `--guided` 开关（默认开启），驱动 Orchestrator。
  - CLI 交互：打印选项编号，读取用户选择；保留原 `--once` 模式。
- 配置：`config/settings.example.yaml`
  - `qa.guided.enabled`、`qa.guided.slots`、`qa.guided.templates_path`、`qa.guided.suggestion_count`、`qa.guided.gap_similarity_threshold`。
- 数据：新增模板文件 `src/prompts/guided_templates.yaml`（槽位、推荐问题、文案片段）。
- 监控：在现有 QA 日志中新增 `dialogue_phase`、`slots_filled`、`suggestions_shown`、`path_taken`。

## 7. 数据结构与接口
- `DialogueState`：
  - `question_raw`、`question_norm`、`slots: dict[str, str]`
  - `last_phase`（clarify/fill_slots/retrieve/gap/follow_up）
  - `suggested_questions: list[str]`
- Orchestrator 主要方法：
  - `clarify(question) -> Message`
  - `apply_slot_selection(selection) -> UpdatedState`
  - `prepare_query(state) -> (query_text, filters, metadata)`
  - `post_answer(state, answer, retrieval_score) -> Message`
- LLM 交互与安全：
  - 使用 `src/prompts/guided_llm.txt` 单模板，要求输出 JSON（受控槽位 + 文案）。
  - 温度 0.1–0.3，超时/解析失败时回退静态模板，确保检索过滤可控。
  - 槽位值必须在配置列表内；不确定留空，不写入 filters。
  - 上下文约束：模板需包含 `history`（最近 2 轮问答）与 `recent_suggestions`，指示“避免重复提相同问题/建议”；当用户重复提问时，指示输出“已回答/是否需要更新槽位或查看其他模块”的轻量文案。
  - 槽位过滤：模板中显式提供 `filled_slots`，要求 LLM 不再提出这些槽位，且生成的 `slot_candidates` 必须排除已填项；生成 follow-up 时也不得推荐已解决/已填槽位对应的模块。

## 7.1 LLM 编排规则（可抽象成模板变量 + 校验函数）
- 输入上下文：`question_raw`、`history`（最近 2 轮 QA）、`filled_slots`、`recent_suggestions`、`module_hit`、`gap_reason`（空结果/低分）。
- 生成物必须是 JSON，字段限定：
  - clarify 模式：`{"clarify_text": str, "slot_candidates": {"phase": [...], "module": [...], ...}}`
  - slot_fill 模式：`{"slots": {"phase": "", "module": "", "project_name": "", "timeframe": ""}}`
  - follow_up 模式：`{"follow_ups": ["..",".."]}`
  - gap_prompt 模式：`{"gap_questions": ["..","..",".."]}`
- 受控词表：`slot_candidates` 与 `slots` 的值必须来自 `slot_schema`；若不确定留空。
- 去重规则：`filled_slots` 中的键不再出现在 `slot_candidates`；`recent_suggestions` 不再在本轮 follow-up / gap 中出现；同一 `module_hit` 的建议 2 轮内不重复。
- 重复问题处理：如 `question_raw` 与 `history` 最近一问语义接近（LLM 内部判断或由上层传 flag），返回简短提示“已回答/是否更新槽位/是否查看其他模块”，不再重复澄清。
- 安全与回退：解析失败、JSON 不合法或出现未授权槽位值时，立即回退静态模板；同时标记 `last_phase=clarify_fallback/gap_fallback` 便于监控。
- 长度与风格：clarify_text ≤ 50 字，follow_up / gap 问句 ≤ 30 字，口吻简洁、避免使用表情和第一人称。

## 7.2 鲁棒性与防重复策略
- 可回答性检测：在进入 follow_up/gap 前先做“可回答/不可回答”判定，低置信触发拒答或补槽位分支，避免幻觉。
- 语义去重：维护最近问答/建议的语义缓存，阈值≥0.9 视为重复，直接提示“已回答/是否更新槽位”并复用答案。
- 槽位鲁棒填充：优先 LLM 受控词表输出，解析失败时回退规则/正则零样本填充，减少话题切换时的漏填。
- 结构化校验：LLM JSON 输出经模式校验（Pydantic/JSON Schema），不合法即降级模板，并记录 `phase=*_fallback`。
- 成本与截断：设置温度低、max_tokens 受限；按模式给定 token 预算，避免冗长生成。
- 重复槽位冷却：`filled_slots` 与 `recent_suggestions` 作为冷却列表传入 LLM，禁止再次请求/推荐已填槽位或最近 2 轮建议。
- 降级链路：LLM → 语义缓存 → 静态模板三段式；任意一步超时/越权/解析失败即降级，并在状态中标记。
- 话题切换防漂移：若新问题与 history 语义相似度低，则重置除稳态槽位（如 project_name）外的临时槽位，并询问是否沿用旧槽位。
- 监控指标：新增 `repeat_blocked_count`、`fallback_rate`、`unanswerable_detected`，用于评估鲁棒性与防重复效果。

## 8. 流程落地（PoC → 增强）
1) **PoC（1 天）**：CLI 版引导模式，固定槽位与文案；命中失败时返回预置三条追问；日志记录新增字段。
2) **Config 化（1 天）**：引入 `guided_templates.yaml`，支持按项目/阶段选择模板；`settings.yaml` 增加开关与阈值。
3) **智能推荐（1–2 天）**：依据最近命中文档的 `module` 元数据，动态推荐“下一步”问题；低置信时自动切换到 gap 分支。
4) **多通道（可选）**：如果后续接入 Web/IM，可复用 Orchestrator，CLI 仅作为示例客户端。

## 9. 测试与验证
- 单测：`tests/test_dialogue_orchestrator.py` 覆盖槽位合并、模板选择、无结果分支。
- 集成/烟测：`tests/test_qa_cli_guided_smoke.py`（LLM mock、固定检索结果），验证澄清→检索→引导链路。
- 指标校验：对比 guided on/off 的命中率与“无结果”占比（使用 QA 监控日志）；检查配置热加载/回退。

## 10. 风险与对策
- 文案适配度不足：保留配置化模板，允许运营快速迭代；CLI 支持 `--guided-off` 回退。
- 槽位噪声影响检索：在 `enrich_query` 中限制可用槽位字段，并设置信任度阈值（未填充时不降权原 query）。
- 交互步骤过长：默认最多两轮澄清；用户直接输入问题时可跳过澄清进入检索。
- 监控膨胀：复用现有采样开关，新增字段遵循采样规则。

## 11. 交付物与文档同步
- 代码：`src/qa/dialogue_orchestrator.py`、`src/prompts/guided_templates.yaml`、`qa_cli` 改造。
- 配置：`config/settings.example.yaml` 新增 guided 配置段。
- 文档：本文件；如调整 CLI 参数/目录，需同步根 `AGENTS.md` 与 `src/AGENTS.md`、`src/scripts/AGENTS.md` 说明。
- 日志：沿用 `logs/qa_sessions/`，新增 `dialogue_phase` 等字段，无需新目录。
