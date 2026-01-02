"""引导式对话编排器（阶段 1 模板版）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:  # LangGraph 可选，便于无依赖环境降级
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - 安全降级
    StateGraph = None
    END = None

from src.qa.qa_engine import QAEngine


@dataclass
class DialogueState:
    """对话状态，跨轮次保持。"""

    question_raw: str = ""
    slots: Dict[str, str] = field(default_factory=dict)  # project_name, phase, module
    history: List[Dict[str, str]] = field(default_factory=list)  # [{q, a}]
    recent_suggestions: List[str] = field(default_factory=list)
    last_phase: str = "init"
    last_result: Dict[str, Any] = field(default_factory=dict)


class DialogueOrchestrator:
    """封装 QAEngine，为 Gradio/CLI 提供引导式对话能力。"""

    def __init__(
        self,
        qa_engine: QAEngine,
        templates: Dict[str, Any],
        llm_client: Optional[Any] = None,
        gap_threshold: float = 0.5,
    ):
        self.qa_engine = qa_engine
        self.templates = templates or {}
        self.llm = llm_client  # 预留阶段 3
        self.gap_threshold = gap_threshold
        self.graph = self.build_graph() if StateGraph else None

    # ---- LangGraph 编排 ----
    def build_graph(self):
        graph = StateGraph(DialogueState)
        graph.add_node("retrieve", self.retrieve_node)
        graph.add_node("gap_prompt", self.gap_prompt_node)
        graph.add_node("follow_up", self.follow_up_node)
        graph.add_conditional_edges("retrieve", self.route_after_retrieve)
        graph.add_edge("gap_prompt", END)
        graph.add_edge("follow_up", END)
        graph.set_entry_point("retrieve")
        return graph.compile()

    def retrieve_node(self, state: DialogueState) -> DialogueState:
        project_name = state.slots.get("project_name")
        result = self.qa_engine.answer(
            question=state.question_raw,
            project_name=project_name,
            top_k=8,
            top_n=5,
            tau=0.5,
        )
        state.last_result = result
        state.last_phase = "retrieve"
        state.history.append({"q": state.question_raw, "a": result.get("answer", "")[:100]})
        return state

    def route_after_retrieve(self, state: DialogueState) -> str:
        res = state.last_result or {}
        top_score = self._best_similarity(res.get("sources", []))
        if res.get("status") == "no_context" or top_score < self.gap_threshold:
            return "gap_prompt"
        return "follow_up"

    def gap_prompt_node(self, state: DialogueState) -> DialogueState:
        res = state.last_result or {}
        res["suggestions"] = self._generate_gap_prompts(state)
        res["dialogue_phase"] = "gap_prompt"
        state.recent_suggestions = res["suggestions"][:3]
        state.last_phase = "gap_prompt"
        state.last_result = res
        return state

    def follow_up_node(self, state: DialogueState) -> DialogueState:
        res = state.last_result or {}
        res["suggestions"] = self._generate_follow_ups(res.get("sources", []), state)
        res["dialogue_phase"] = "follow_up"
        state.recent_suggestions = res["suggestions"][:3]
        state.last_phase = "follow_up"
        state.last_result = res
        return state

    # ---- 公共方法 ----
    def answer_with_guidance(self, question: str, state: Optional[DialogueState] = None) -> Dict[str, Any]:
        """对外单轮接口：输入问题，返回带引导建议的结果。"""
        state = state or DialogueState()
        state.question_raw = question

        if self.graph:
            state = self.graph.invoke(state)
        else:  # 无 LangGraph 时的降级顺序
            state = self.retrieve_node(state)
            next_step = self.route_after_retrieve(state)
            state = self.gap_prompt_node(state) if next_step == "gap_prompt" else self.follow_up_node(state)

        return state.last_result

    # ---- 辅助 ----
    def _best_similarity(self, sources: List[Dict[str, Any]]) -> float:
        sims = [s.get("similarity") for s in sources if s.get("similarity") is not None]
        return max(sims) if sims else 0.0

    def _generate_gap_prompts(self, state: DialogueState) -> List[str]:
        prompts = list(self.templates.get("gap_prompts", [])) or [
            "要不要告诉我项目名称？",
            "您关注哪个阶段？立项/实施/收尾",
            "想了解功能、架构还是部署？",
        ]
        # 已填槽位的提示做简单过滤
        if state.slots.get("project_name"):
            prompts = [p for p in prompts if "项目" not in p]
        return prompts[:3]

    def _generate_follow_ups(self, sources: List[Dict[str, Any]], state: DialogueState) -> List[str]:
        modules = self._extract_modules(sources)
        follow_by_module = self.templates.get("follow_ups_by_module", {})
        collected: List[str] = []
        for m in modules:
            collected.extend(follow_by_module.get(m, []))
        if not collected:
            collected = follow_by_module.get("default", [])
        # 去重（与近期建议）
        deduped = []
        for s in collected:
            if s not in deduped and s not in state.recent_suggestions:
                deduped.append(s)
        return (deduped or follow_by_module.get("default", []))[:3]

    @staticmethod
    def _extract_modules(sources: List[Dict[str, Any]]) -> List[str]:
        modules = []
        for src in sources:
            page_type = src.get("page_type") or []
            if isinstance(page_type, str):
                page_type = [page_type]
            for m in page_type:
                if m not in modules:
                    modules.append(m)
        return modules


__all__ = ["DialogueOrchestrator", "DialogueState"]
