"""引导式对话编排器（阶段 3 增强版：LLM 澄清 + 去重冷却 + 监控字段）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

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
    question_norm: str = ""
    slots: Dict[str, str] = field(default_factory=dict)  # project_name, phase, module
    history: List[Dict[str, str]] = field(default_factory=list)  # [{q, a}]
    recent_suggestions: List[str] = field(default_factory=list)
    suggestion_cooldown: Dict[str, int] = field(default_factory=dict)
    repeat_blocked_count: int = 0
    last_phase: str = "init"
    last_result: Dict[str, Any] = field(default_factory=dict)
    question_enriched: str = ""
    fallback_used: bool = False
    graph_attempt: int = 1
    retrieval_params: Dict[str, Any] = field(default_factory=dict)
    allow_all_projects: bool = False


class DialogueOrchestrator:
    """封装 QAEngine，为 CLI 等调用提供引导式对话能力。"""

    def __init__(
        self,
        qa_engine: QAEngine,
        templates: Dict[str, Any],
        llm_client: Optional[Any] = None,
        gap_threshold: float = 0.5,
        llm_prompt_path: Optional[str] = None,
        **kwargs: Any,
    ):
        self.qa_engine = qa_engine
        self.templates = templates or {}
        self.llm = llm_client  # 阶段 3：用于生成追问/澄清
        self.gap_threshold = gap_threshold
        self.llm_prompt_path = Path(llm_prompt_path).resolve() if llm_prompt_path else None
        self.graph = self.build_graph() if StateGraph else None
        self.llm_prompt = self._load_llm_prompt()

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
        params = state.retrieval_params or {"top_k": 8, "top_n": 5, "tau": 0.5}
        question = state.question_enriched or state.question_raw
        result = self.qa_engine.answer(
            question=question,
            project_name=project_name,
            top_k=params.get("top_k", 8),
            top_n=params.get("top_n", 5),
            tau=params.get("tau", 0.5),
        )
        state.last_result = result
        state.last_phase = "retrieve"
        state.history.append({"q": question, "a": result.get("answer", "")[:100]})
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
        state.last_phase = "gap_prompt"
        state.last_result = res
        return state

    def follow_up_node(self, state: DialogueState) -> DialogueState:
        res = state.last_result or {}
        res["suggestions"] = self._generate_follow_ups(res.get("sources", []), state)
        res["dialogue_phase"] = "follow_up"
        state.last_phase = "follow_up"
        state.last_result = res
        return state

    # ---- 公共方法 ----
    def answer_with_guidance(
        self,
        question: str,
        state: Optional[DialogueState] = None,
        *,
        project_name: Optional[str] = None,
        top_k: int = 8,
        top_n: int = 5,
        tau: float = 0.5,
        allow_all_projects: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """对外单轮接口：输入问题，返回带引导建议的结果。"""
        state = state or DialogueState()
        state.question_raw = question
        state.fallback_used = False  # reset per turn
        state.retrieval_params = {"top_k": top_k, "top_n": top_n, "tau": tau}
        state.allow_all_projects = state.allow_all_projects or allow_all_projects
        if project_name is not None:
            state.slots["project_name"] = project_name

        clarify = self.clarify_if_needed(question, state, allow_all_projects=state.allow_all_projects)
        if clarify.get("needs_clarify"):
            result = {
                "answer": clarify.get("clarify_text", "请补充项目名称"),
                "sources": [],
                "status": "clarify",
                "dialogue_phase": "clarify",
                "slot_candidates": clarify.get("slot_candidates", {}),
            }
            state.last_result = result
            state.last_phase = "clarify"
            self._log_dialogue_metrics(state)
            return result

        state.question_enriched = self.enrich_query(question, state.slots)

        try:
            if self.graph:
                state = self.graph.invoke(state)
            else:  # 无 LangGraph 时的降级顺序
                state = self.retrieve_node(state)
                next_step = self.route_after_retrieve(state)
                state = self.gap_prompt_node(state) if next_step == "gap_prompt" else self.follow_up_node(state)
        except Exception as exc:
            state.fallback_used = True
            fallback = self.qa_engine.answer(
                question=state.question_enriched or state.question_raw,
                project_name=state.slots.get("project_name"),
                top_k=top_k,
                top_n=top_n,
                tau=tau,
            )
            fallback["status"] = fallback.get("status", "success")
            fallback["dialogue_phase"] = "fallback"
            fallback["error"] = str(exc)
            state.last_result = fallback
            state.last_phase = "fallback"

        self._log_dialogue_metrics(state)
        return state.last_result

    # ---- 辅助 ----
    def _best_similarity(self, sources: List[Dict[str, Any]]) -> float:
        sims = [s.get("similarity") for s in sources if s.get("similarity") is not None]
        return max(sims) if sims else 0.0

    def _load_llm_prompt(self) -> Optional[str]:
        prompt_path = (
            self.llm_prompt_path
            or Path(__file__).resolve().parent.parent / "prompts" / "guided_llm.txt"
        )
        if prompt_path and Path(prompt_path).exists():
            return Path(prompt_path).read_text(encoding="utf-8")
        return None

    # ---- 槽位澄清（阶段 2） ----
    def clarify_if_needed(self, question: str, state: DialogueState, allow_all_projects: bool = False) -> Dict[str, Any]:
        """缺项目名时返回澄清信息；若问题中含项目则直接填充。"""
        if state.slots.get("project_name") or allow_all_projects:
            return {"needs_clarify": False}

        detected = self._detect_project_in_question(question)
        if detected:
            state.slots["project_name"] = detected
            return {"needs_clarify": False}

        candidates = self._list_available_projects()
        prompt = self.templates.get("slot_schema", {}).get("project_name", {}).get("prompt", "请问您想了解哪个项目？")

        if self.llm and self.llm_prompt:
            llm_res = self._clarify_with_llm(question, state, candidates)
            if llm_res:
                return {"needs_clarify": True, **llm_res}
        return {
            "needs_clarify": True,
            "clarify_text": prompt,
            "slot_candidates": {"project_name": candidates},
        }

    @staticmethod
    def apply_slot_selection(selection: Dict[str, str], state: DialogueState) -> DialogueState:
        """用户选择后更新槽位。"""
        state.slots.update(selection or {})
        return state

    @staticmethod
    def enrich_query(question: str, slots: Dict[str, str]) -> str:
        """将槽位拼接到检索 query。"""
        enriched = question
        if slots.get("project_name"):
            enriched = f"[项目:{slots['project_name']}] {question}"
        return enriched

    def _detect_project_in_question(self, question: str) -> Optional[str]:
        projects = self._list_available_projects()
        question_lower = question.lower()
        for name in projects:
            if name.lower() in question_lower:
                return name
        return None

    def _list_available_projects(self) -> List[str]:
        projects: List[str] = []
        try:
            store = getattr(self.qa_engine, "store", None)
            if store and hasattr(store, "list_projects"):
                projects.extend(store.list_projects())
        except Exception:
            pass
        # 与 UI 同源：扫描 ppt_outputs 下已生成向量的项目
        ppt_outputs = Path("ppt_outputs")
        if ppt_outputs.exists():
            for item in ppt_outputs.iterdir():
                if item.is_dir() and (item / "embeddings" / "rag_documents.json").exists():
                    projects.append(item.name)
        # 去重并排序
        return sorted({p for p in projects if p})

    def _generate_gap_prompts(self, state: DialogueState) -> List[str]:
        prompts = list(self.templates.get("gap_prompts", [])) or [
            "请先选定要问的项目名称",
            "想了解功能还是部署/案例？",
        ]
        # 已填槽位的提示做简单过滤
        if state.slots.get("project_name"):
            prompts = [p for p in prompts if "项目" not in p]
        return self._filter_duplicates(prompts, state)

    def _generate_follow_ups(self, sources: List[Dict[str, Any]], state: DialogueState) -> List[str]:
        modules = self._extract_modules(sources)
        # 阶段 3：优先使用 LLM 生成
        if self.llm and self.llm_prompt:
            generated = self._generate_with_llm(state.question_raw, state, modules, mode="follow_up")
            if generated and generated.get("follow_ups"):
                return self._filter_duplicates(generated["follow_ups"], state)

        follow_by_module = self.templates.get("follow_ups_by_module", {})
        collected: List[str] = []
        for m in modules:
            collected.extend(follow_by_module.get(m, []))
        if not collected:
            collected = follow_by_module.get("default", [])
        return self._filter_duplicates(collected or follow_by_module.get("default", []), state)

    # ---- LLM 生成与去重（阶段 3） ----
    def _generate_with_llm(self, question: str, state: DialogueState, modules: List[str], mode: str = "follow_up") -> Dict[str, Any]:
        if not self.llm_prompt or not self.llm:
            return {}

        prompt = self._build_llm_prompt(question, state, modules)
        try:
            raw = self.llm.generate(prompt)
            parsed = self._parse_llm_json(raw)
            if not self._validate_llm_output(parsed, mode=mode):
                raise ValueError("Invalid LLM output")
            return parsed
        except Exception:
            state.fallback_used = True
            return self._fallback_to_template(modules, state, mode=mode)

    def _build_llm_prompt(self, question: str, state: DialogueState, modules: List[str]) -> str:
        replacements = {
            "{question}": question,
            "{filled_slots}": json.dumps(state.slots, ensure_ascii=False),
            "{recent_suggestions}": json.dumps(state.recent_suggestions, ensure_ascii=False),
            "{module_hit}": json.dumps(modules, ensure_ascii=False),
        }
        prompt = self.llm_prompt
        for key, val in replacements.items():
            prompt = prompt.replace(key, val)
        return prompt

    @staticmethod
    def _parse_llm_json(raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw, flags=re.S)
            if match:
                return json.loads(match.group())
            raise

    def _validate_llm_output(self, output: Dict[str, Any], mode: str = "follow_up") -> bool:
        if not isinstance(output, dict):
            return False
        if mode == "clarify":
            clarify = output.get("clarify_text")
            slot_candidates = output.get("slot_candidates", {})
            if not clarify or not isinstance(clarify, str):
                return False
            if slot_candidates is not None and not isinstance(slot_candidates, dict):
                return False
            return True
        follow_ups = output.get("follow_ups")
        return bool(follow_ups and isinstance(follow_ups, list))

    def _fallback_to_template(self, modules: List[str], state: DialogueState, mode: str = "follow_up") -> Dict[str, Any]:
        if mode == "clarify":
            prompt = self.templates.get("slot_schema", {}).get("project_name", {}).get("prompt", "请问您想了解哪个项目？")
            return {"clarify_text": prompt, "slot_candidates": {"project_name": self._list_available_projects()}}
        return {"follow_ups": self._filter_duplicates(self._template_followups(modules), state)}

    def _template_followups(self, modules: List[str]) -> List[str]:
        follow_by_module = self.templates.get("follow_ups_by_module", {})
        collected: List[str] = []
        for m in modules:
            collected.extend(follow_by_module.get(m, []))
        if not collected:
            collected = follow_by_module.get("default", [])
        return collected

    def _filter_duplicates(self, suggestions: List[str], state: DialogueState) -> List[str]:
        self._tick_cooldown(state)
        filtered: List[str] = []
        for s in suggestions:
            if s in state.recent_suggestions:
                state.repeat_blocked_count += 1
                state.suggestion_cooldown[s] = max(state.suggestion_cooldown.get(s, 0), 2)
                continue
            if self._is_semantically_similar(s, state.recent_suggestions):
                state.repeat_blocked_count += 1
                state.suggestion_cooldown[s] = max(state.suggestion_cooldown.get(s, 0), 2)
                continue
            if s not in filtered:
                filtered.append(s)
        for s in filtered:
            state.suggestion_cooldown[s] = 2
        state.recent_suggestions = (filtered + state.recent_suggestions)[:10]
        # 限制前端展示数量，避免“选项过载”
        return filtered[:2]

    @staticmethod
    def _is_semantically_similar(text: str, corpus: List[str], threshold: float = 0.9) -> bool:
        for item in corpus:
            if SequenceMatcher(None, text.lower(), item.lower()).ratio() >= threshold:
                return True
        return False

    @staticmethod
    def _tick_cooldown(state: DialogueState) -> None:
        expired = set()
        for key, val in list(state.suggestion_cooldown.items()):
            if val <= 1:
                state.suggestion_cooldown[key] = 0
                expired.add(key)
            else:
                state.suggestion_cooldown[key] = val - 1
        if expired:
            state.recent_suggestions = [s for s in state.recent_suggestions if s not in expired]

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

    # ---- 监控字段补充 ----
    def _log_dialogue_metrics(self, state: DialogueState) -> None:
        monitor = getattr(self.qa_engine, "monitor", None)
        if not monitor:
            return
        event = {
            "trace_id": monitor.make_trace_id(),
            "question_raw": state.question_raw,
            "question_enriched": state.question_enriched,
            "project_name": state.slots.get("project_name"),
            "dialogue_phase": state.last_phase,
            "graph_node": state.last_phase,
            "graph_attempt": state.graph_attempt,
            "slots_filled": state.slots,
            "suggestions_shown": state.last_result.get("suggestions", []),
            "repeat_blocked_count": state.repeat_blocked_count,
            "fallback_used": state.fallback_used,
            "fallback_rate": 1.0 if state.fallback_used else 0.0,
            "path_taken": state.last_phase,
            "unanswerable_detected": state.last_result.get("status") == "no_context",
        }
        monitor.log_event(event)

    def _clarify_with_llm(self, question: str, state: DialogueState, candidates: List[str]) -> Optional[Dict[str, Any]]:
        generated = self._generate_with_llm(question, state, modules=[], mode="clarify")
        if not generated:
            return None
        clarify_text = generated.get("clarify_text")
        slot_candidates = generated.get("slot_candidates") or {}
        slot_candidates.setdefault("project_name", candidates)
        return {
            "clarify_text": clarify_text or "请问您想了解哪个项目？",
            "slot_candidates": slot_candidates,
        }


__all__ = ["DialogueOrchestrator", "DialogueState"]
