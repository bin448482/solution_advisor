# QA 引导式对话 - 完整实施计划

## 目标
将现有单轮 QA 系统扩展为引导式多轮对话，支持交互式 CLI 模式。

## 用户选择
- **实施范围**：全部三阶段
- **交互模式**：交互式多轮 CLI
- **编排框架**：LangChain Agents + LangGraph（LCEL）。当前仅实现 LangGraph 路径；`legacy` 回退未实现，如需纯函数版需后续补充。

## 总体架构
```
用户输入
  ↓
[qa_cli.py] --guided 模式，交互式循环
  ↓
[DialogueOrchestrator]（LangGraph 节点图）状态管理 + 编排
  ├─ clarify_if_needed() → 槽位澄清
  ├─ answer_with_guidance() → 包装 QAEngine
  └─ generate_suggestions() → LLM/模板生成追问
  ↓
[QAEngine.answer()] 原有检索 + LLM 回答
  ↓
输出答案 + 建议选项 → 用户选择 → 循环
```

---

## 阶段 1：最小可行版（Gap Prompt + 模板化 Follow-up）

### 目标
- 检测"无结果"场景，返回引导性追问
- 命中时附带 2-3 条模板化后续建议
- 不引入槽位系统，不改动 QAEngine 核心逻辑
- 建立 LangGraph 最小骨架（节点：`retrieve`、`gap_prompt`、`follow_up`），CLI 开关默认使用 LangGraph。

### 改动文件

**1. 新增 `src/qa/dialogue_orchestrator.py`**
```python
"""引导式对话编排器，包装 QAEngine 实现多轮对话（LangGraph）。"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json

from src.qa.qa_engine import QAEngine
from src.summarizer.llm_client import LLMClient
from langgraph.graph import StateGraph, END


@dataclass
class DialogueState:
    """对话状态，跨轮次保持。"""
    question_raw: str = ""
    slots: Dict[str, str] = field(default_factory=dict)  # project_name, phase, module
    history: List[Dict[str, str]] = field(default_factory=list)  # [{q, a}]
    recent_suggestions: List[str] = field(default_factory=list)  # 去重用
    last_phase: str = "init"  # init/clarify/retrieve/gap/follow_up


class DialogueOrchestrator:
    """编排引导式对话流程（LangGraph 版）。"""

    def __init__(self, qa_engine: QAEngine, templates: Dict[str, Any], llm_client: Optional[LLMClient] = None):
        self.qa_engine = qa_engine
        self.templates = templates
        self.llm = llm_client
        self.graph = self.build_graph()

    # ---- LangGraph 定义 ----
    def build_graph(self):
        graph = StateGraph(DialogueState)
        graph.add_node("retrieve", self.retrieve_node)
        graph.add_node("gap_prompt", self.gap_prompt_node)
        graph.add_node("follow_up", self.follow_up_node)
        graph.add_edge("gap_prompt", END)
        graph.add_edge("follow_up", END)
        graph.add_conditional_edges("retrieve", self.route_after_retrieve)
        graph.set_entry_point("retrieve")
        return graph.compile()

    def retrieve_node(self, state: DialogueState):
        project_name = state.slots.get("project_name")
        result = self.qa_engine.answer(
            question=state.question_raw,
            project_name=project_name,
            top_k=8,
            top_n=5,
            tau=0.5,
        )
        state.history.append({"q": state.question_raw, "a": result.get("answer", "")[:100]})
        state.last_phase = "retrieve"
        state.last_result = result
        return state

    def route_after_retrieve(self, state: DialogueState):
        res = state.last_result
        if res["status"] == "no_context" or res.get("score", 0) < 0.5:
            return "gap_prompt"
        return "follow_up"

    def gap_prompt_node(self, state: DialogueState):
        res = state.last_result
        res["suggestions"] = self._generate_gap_prompt(state.question_raw, state)
        res["dialogue_phase"] = "gap_prompt"
        state.last_phase = "gap_prompt"
        state.recent_suggestions = res["suggestions"][:3]
        state.last_result = res
        return state

    def follow_up_node(self, state: DialogueState):
        res = state.last_result
        res["suggestions"] = self._generate_follow_ups(res.get("sources", []), state)
        res["dialogue_phase"] = "follow_up"
        state.last_phase = "follow_up"
        state.recent_suggestions = res["suggestions"][:3]
        state.last_result = res
        return state

    def _generate_gap_prompt(self, question: str, state: DialogueState) -> List[str]:
        """无结果时生成引导问题（模板 → LLM 降级）。"""
        # 阶段 1：纯模板
        prompts = self.templates.get("gap_prompts", [])[:3]
        # 过滤已填槽位相关的提示
        if state.slots.get("project_name"):
            prompts = [p for p in prompts if "项目" not in p]
        return prompts

    def _generate_follow_ups(self, sources: List[Dict], state: DialogueState) -> List[str]:
        """基于命中模块生成后续建议。需要 sources 含 page_type."""
        modules = {m for src in sources for m in src.get("page_type", [])}
        default = self.templates.get("follow_ups_by_module", {}).get("default", [])
        picked = []
        for m in modules:
            picked.extend(self.templates.get("follow_ups_by_module", {}).get(m, []))
        if not picked:
            picked = default
        filtered = [s for s in picked if s not in state.recent_suggestions]
        return filtered[:2] or default[:2]
```

**2. 新增 `src/prompts/guided_templates.yaml`**
```yaml
gap_prompts:
  - "您可以补充项目名称，例如：ChatBI 的 XXX"
  - "您想了解哪个阶段？立项 / 实施 / 收尾"
  - "您关注哪个方面？功能 / 架构 / 部署 / 案例"

follow_ups_by_module:
  architecture:
    - "想了解部署方式吗？"
    - "需要查看技术栈详情吗？"
  features:
    - "想看具体的功能演示吗？"
    - "需要了解使用场景吗？"
  deployment:
    - "想了解性能指标吗？"
    - "需要查看集成方式吗？"
  default:
    - "还有其他问题吗？"
    - "需要更详细的说明吗？"
```

**3. 扩展 `src/scripts/qa_cli.py`**
```python
# 新增 imports
import yaml
from src.qa.dialogue_orchestrator import DialogueOrchestrator, DialogueState

# 新增参数（Click）
@click.option("--guided", is_flag=True, help="启用引导式多轮对话模式")

# 加载模板函数
def load_guided_templates(path: str = "src/prompts/guided_templates.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# 交互式循环（在 cli 函数内，统一 Click 风格）
def guided_loop(orchestrator: DialogueOrchestrator, initial_question: str = None, project: str = None):
    state = DialogueState()
    if project:
        state.slots["project_name"] = project

    question = initial_question
    while True:
        if not question:
            question = click.prompt("\n🔍 请输入问题（q 退出）", default="", show_default=False)
            if question.lower() in ("q", "quit", "exit", ""):
                break

        state.question_raw = question
        state = orchestrator.graph.invoke(state)
        result = state.last_result

        click.echo(f"\n📝 {result.get('answer', '')}")
        if result.get("sources"):
            click.echo("   来源: " + ", ".join(
                f\"{s['project']}:第{s['slide_no']}页\" for s in result.get(\"sources\", [])[:3]
            ))

        suggestions = result.get("suggestions", [])
        if suggestions:
            click.echo("\n💡 您可能还想问：")
            for i, s in enumerate(suggestions, 1):
                click.echo(f"  {i}. {s}")
            choice = click.prompt("请选择（0 输入新问题）", default="0", show_default=False)
            if choice.isdigit() and 1 <= int(choice) <= len(suggestions):
                question = suggestions[int(choice) - 1]
                continue

        question = None
    click.echo("\n👋 再见！")

# 在 cli() 主函数中
if guided:
    templates = load_guided_templates()
    orchestrator = DialogueOrchestrator(qa_engine, templates)
    guided_loop(orchestrator, question, project)
else:
    result = qa_engine.answer(...)
```

**4. 扩展 `config/settings.example.yaml`**
```yaml
qa:
  guided:
    enabled: true
    engine: langgraph          # 目前仅支持 langgraph；legacy 待实现
    suggestion_count: 3
    templates_path: src/prompts/guided_templates.yaml
```

### 验收标准
- `--guided` 模式下，无结果时显示 3 条引导问题
- 有结果时显示 2 条基于模块的后续建议
- 日志中记录 `dialogue_phase`、`graph_node` 字段
- `qa.guided.engine` 仅接受 `langgraph`；若用户传 `legacy`，CLI 需提示“未实现，已回退到 langgraph”。

### 预估工时：1-2 天

### 监控与日志要求（同步到各阶段）
- 记录 `dialogue_phase`、`graph_node`、`graph_attempt`。
- 记录鲁棒性指标：`repeat_blocked_count`、`fallback_rate`、`unanswerable_detected`。
- 在 `sources` 中带回 `page_type` 以支持后续建议决策。

---

## 阶段 2：槽位澄清（Project Name 优先）

### 目标
- 首轮检测缺失的 `project_name`，主动询问
- 用户补充后，将槽位拼接到检索 query
- 验证命中率提升是否达标（≥10%）
- 补齐基础方法：`_detect_project_in_question`（基于项目列表关键词匹配）、`_list_available_projects`（调用 `ChromaStore.list_projects()`）。
- 统一 sources 元数据：QAEngine 返回 `page_type`、`level`、`project`、`slide_no`，供后续建议生成。

### 改动文件

**1. 扩展 `DialogueOrchestrator`**
```python
class DialogueState:
    question_raw: str
    question_norm: str
    slots: Dict[str, str]  # project_name, phase, module
    last_phase: str
    history: List[Dict]  # 最近 2 轮 QA

class DialogueOrchestrator:
    def clarify_if_needed(self, question, state):
        """检测是否需要澄清"""
        if not state.slots.get("project_name"):
            # 检查问题中是否已包含项目名
            detected = self._detect_project_in_question(question)
            if not detected:
                return {
                    "needs_clarify": True,
                    "clarify_text": "请问您想了解哪个项目？",
                    "slot_candidates": {"project_name": self._list_available_projects()}
                }
        return {"needs_clarify": False}

    def apply_slot_selection(self, selection, state):
        """用户选择后更新槽位"""
        state.slots.update(selection)
        return state

    def enrich_query(self, question, slots):
        """将槽位拼接到检索 query"""
        enriched = question
        if slots.get("project_name"):
            enriched = f"[项目:{slots['project_name']}] {question}"
        return enriched
```

**2. 扩展 CLI 交互**
```python
# 交互式槽位收集
if args.guided:
    state = DialogueState()
    clarify = orchestrator.clarify_if_needed(args.question, state)

    if clarify["needs_clarify"]:
        print(clarify["clarify_text"])
        for i, p in enumerate(clarify["slot_candidates"]["project_name"], 1):
            print(f"  {i}. {p}")
        choice = input("请选择（输入序号或项目名）: ")
        state = orchestrator.apply_slot_selection({"project_name": choice}, state)

    # 使用增强后的 query
    enriched_q = orchestrator.enrich_query(args.question, state.slots)
    result = orchestrator.answer_with_guidance(enriched_q, state.slots.get("project_name"))
```

**3. 扩展模板**
```yaml
slot_schema:
  project_name:
    prompt: "请问您想了解哪个项目？"
    required: false
  phase:
    prompt: "您关注哪个阶段？"
    options: ["立项", "实施", "收尾"]
  module:
    prompt: "您关注哪个方面？"
    options: ["功能", "架构", "部署", "案例", "风险"]
```

### 验收标准
- 缺少 project_name 时主动询问
- 用户选择后，检索使用增强 query
- 对比实验：guided on/off 命中率差异 ≥10%

### 预估工时：2-3 天

---

## 阶段 3：LLM 智能追问（可选）

### 目标
- 用 LLM 生成个性化 clarify/follow-up
- 实现去重与冷却机制
- 支持多轮对话状态管理

### 改动文件

**1. 新增 `src/prompts/guided_llm.txt`**
```
你是一个项目咨询助手。根据用户问题和上下文，生成引导性追问。

输入：
- question: {question}
- filled_slots: {filled_slots}
- recent_suggestions: {recent_suggestions}
- module_hit: {module_hit}

输出 JSON：
{
  "clarify_text": "...",  // ≤50字
  "slot_candidates": {"phase": [...], "module": [...]},
  "follow_ups": ["...", "..."]  // 2-3条，每条≤30字
}

规则：
- 不要重复 filled_slots 中已有的槽位
- 不要重复 recent_suggestions 中的建议
- 口吻简洁，避免表情和第一人称
```

**2. 扩展 `DialogueOrchestrator`**
```python
def _generate_with_llm(self, question, state, mode):
    """LLM 生成 clarify/follow-up"""
    prompt = self._build_llm_prompt(question, state, mode)
    try:
        response = self.llm_client.generate(prompt, temperature=0.2, max_tokens=200)
        parsed = json.loads(response)
        # 校验 JSON 结构
        if not self._validate_llm_output(parsed, mode):
            raise ValueError("Invalid LLM output")
        return parsed
    except Exception:
        # 降级到模板
        return self._fallback_to_template(mode, state)

def _validate_llm_output(self, output, mode):
    """校验 LLM 输出是否符合 schema"""
    # 使用 Pydantic 或 JSON Schema 校验
    pass
```

**3. 去重与冷却**
```python
class DialogueState:
    recent_suggestions: List[str]  # 最近 2 轮的建议
    suggestion_cooldown: Dict[str, int]  # module -> 冷却轮数

def _filter_duplicates(self, suggestions, state):
    """过滤重复建议"""
    filtered = []
    for s in suggestions:
        # 语义去重：与 recent_suggestions 相似度 < 0.9
        if not self._is_semantically_similar(s, state.recent_suggestions):
            filtered.append(s)
    return filtered[:3]
```

### 验收标准
- LLM 生成的追问符合 JSON schema
- 解析失败时自动降级到模板
- 同一建议 2 轮内不重复出现
- 日志记录 `fallback_rate` 指标

### 预估工时：3-4 天

---

## 关键文件清单

| 文件 | 阶段 | 改动类型 |
|------|------|----------|
| `src/qa/dialogue_orchestrator.py` | 1 | 新增 |
| `src/prompts/guided_templates.yaml` | 1 | 新增 |
| `src/scripts/qa_cli.py` | 1 | 扩展 |
| `config/settings.example.yaml` | 1 | 扩展 |
| `src/qa/dialogue_state.py` | 2 | 新增 |
| `src/prompts/guided_llm.txt` | 3 | 新增 |
| `tests/test_dialogue_orchestrator.py` | 1 | 新增 |

---

## 风险与缓解

1. **CLI 交互体验差** → 阶段 1 仅展示建议，不强制多轮；阶段 2 可选跳过澄清
2. **LLM 输出不稳定** → 阶段 3 有完整降级链路（LLM → 模板）
3. **槽位噪声影响检索** → 槽位仅用于 project 过滤，不改动 query 语义
4. **成本增加** → 阶段 1-2 不增加 LLM 调用；阶段 3 限制 max_tokens
5. **依赖缺失** → 在 README/requirements 中加入 `langgraph>=0.1.0`；安装失败时 CLI 提示并退出（当前无 legacy 自动降级）。

---

## 交互式 CLI 设计（贯穿三阶段）

### CLI 主循环
```python
# src/scripts/qa_cli.py 扩展

def guided_loop(orchestrator, initial_question=None, project=None):
    """交互式引导对话主循环"""
    state = DialogueState()
    if project:
        state.slots["project_name"] = project

    question = initial_question
    while True:
        # 1. 首轮或无问题时，提示输入
        if not question:
            question = input("\n🔍 请输入问题（输入 q 退出）: ").strip()
            if question.lower() in ("q", "quit", "exit"):
                break

        # 2. 槽位澄清（阶段 2）
        clarify = orchestrator.clarify_if_needed(question, state)
        if clarify["needs_clarify"]:
            print(f"\n💬 {clarify['clarify_text']}")
            for i, opt in enumerate(clarify["options"], 1):
                print(f"  {i}. {opt}")
            choice = input("请选择（序号/名称/跳过按回车）: ").strip()
            if choice:
                state = orchestrator.apply_slot_selection(clarify["slot_key"], choice, state)

        # 3. 执行问答
        result = orchestrator.answer_with_guidance(question, state)

        # 4. 输出答案
        print(f"\n📝 {result['answer']}")
        if result.get("sources"):
            print(f"   来源: {', '.join(s['project'] + ':' + str(s['slide_no']) for s in result['sources'][:3])}")

        # 5. 显示建议选项
        suggestions = result.get("suggestions", [])
        if suggestions:
            print(f"\n💡 您可能还想问：")
            for i, s in enumerate(suggestions, 1):
                print(f"  {i}. {s}")
            print(f"  0. 输入新问题")

            choice = input("请选择（序号）: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(suggestions):
                question = suggestions[int(choice) - 1]
                state.history.append({"q": question, "a": result["answer"][:100]})
                continue

        # 6. 重置问题，等待新输入
        question = None
        state.history.append({"q": question, "a": result.get("answer", "")[:100]})

# CLI 入口
if args.guided:
    guided_loop(orchestrator, args.question, args.project)
```

### 退出条件
- 用户输入 `q`/`quit`/`exit`
- 连续 3 轮无结果
- 用户选择 `0` 后不输入新问题

---

## 实施顺序（推荐）

1. **阶段 1**（1-2 天）
   - DialogueOrchestrator 基础框架
   - 模板化 gap_prompt + follow_up
   - CLI 交互循环骨架

2. **阶段 2**（2-3 天）
   - DialogueState 状态管理
   - 槽位检测与澄清
   - 项目列表动态获取

3. **阶段 3**（3-4 天）
   - LLM 生成追问
   - 去重与冷却机制
   - 降级链路完善

**总预估：6-9 天**

---

## 测试计划

### 单元测试 `tests/test_dialogue_orchestrator.py`
- `test_gap_prompt_on_no_context` - 无结果时返回引导
- `test_follow_up_by_module` - 按模块生成建议
- `test_slot_clarify_missing_project` - 缺项目名时澄清
- `test_slot_apply_selection` - 槽位更新正确
- `test_llm_fallback_on_parse_error` - LLM 失败降级模板
- `test_suggestion_dedup` - 建议去重

### 集成测试 `tests/test_qa_cli_guided_smoke.py`
- Mock LLM + 固定检索结果
- 验证完整交互流程
- 检查日志字段完整性
