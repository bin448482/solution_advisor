import json

import pytest

from src.qa.dialogue_orchestrator import DialogueOrchestrator, DialogueState


class DummyQAEngine:
    def __init__(self, result):
        self.result = result
        self.last_question = None

    def answer(self, question: str, project_name=None, top_k=0, top_n=0, tau=0.0):
        self.last_question = question
        return self.result

    @property
    def store(self):
        class _Store:
            @staticmethod
            def list_projects():
                return ["ChatBI", "DataPilot"]

        return _Store()


def test_gap_prompt_on_no_context():
    qa = DummyQAEngine({"status": "no_context", "sources": [], "answer": ""})
    orchestrator = DialogueOrchestrator(qa_engine=qa, templates={"gap_prompts": ["a", "b", "c"]}, gap_threshold=0.9)
    state = DialogueState(slots={"project_name": "ChatBI"})
    result = orchestrator.answer_with_guidance("问句", state)
    assert result["dialogue_phase"] == "gap_prompt"
    assert result["suggestions"][:2] == ["a", "b"]


def test_follow_up_by_module_and_dedup():
    sources = [{"page_type": ["features"], "similarity": 0.9}]
    qa = DummyQAEngine({"status": "success", "sources": sources, "answer": "ok"})
    templates = {
        "follow_ups_by_module": {
            "features": ["s1", "s2"],
            "default": ["d1"],
        }
    }
    orchestrator = DialogueOrchestrator(qa_engine=qa, templates=templates, gap_threshold=0.1)
    state = DialogueState(recent_suggestions=["s1"], slots={"project_name": "ChatBI"})
    result = orchestrator.answer_with_guidance("问句", state)
    assert result["dialogue_phase"] == "follow_up"
    assert "s1" not in result["suggestions"]  # 去重
    assert "s2" in result["suggestions"]


def test_clarify_missing_project_lists_candidates():
    qa = DummyQAEngine({"status": "no_context", "sources": [], "answer": ""})
    orchestrator = DialogueOrchestrator(qa_engine=qa, templates={}, gap_threshold=0.9)
    result = orchestrator.answer_with_guidance("请问功能", DialogueState())
    assert result["status"] == "clarify"
    assert "project_name" in result.get("slot_candidates", {})
    assert result["slot_candidates"]["project_name"]  # non-empty


def test_apply_slot_selection_and_enrich_query():
    qa = DummyQAEngine({"status": "success", "sources": [], "answer": ""})
    orch = DialogueOrchestrator(qa_engine=qa, templates={}, gap_threshold=0.1)
    state = DialogueState()
    state = orch.apply_slot_selection({"project_name": "ChatBI"}, state)
    result = orch.answer_with_guidance("部署方式", state)
    assert qa.last_question.startswith("[项目:ChatBI]")


def test_llm_fallback_on_bad_json():
    class BadLLM:
        @staticmethod
        def generate(prompt: str):
            return "not-json"

    qa = DummyQAEngine({"status": "success", "sources": [], "answer": "ok"})
    templates = {"follow_ups_by_module": {"default": ["d1", "d2"]}}
    orch = DialogueOrchestrator(qa_engine=qa, templates=templates, llm_client=BadLLM(), gap_threshold=0.1)
    res = orch.answer_with_guidance("hi", DialogueState(slots={"project_name": "ChatBI"}))
    assert res["suggestions"]  # fallback to template


def test_clarify_llm_parsed_and_candidates_filled():
    class ClarifyLLM:
        @staticmethod
        def generate(prompt: str):
            return json.dumps({"clarify_text": "请确认项目", "slot_candidates": {"phase": ["实施"]}})

    qa = DummyQAEngine({"status": "no_context", "sources": [], "answer": ""})
    orch = DialogueOrchestrator(qa_engine=qa, templates={}, llm_client=ClarifyLLM(), gap_threshold=0.9)
    res = orch.answer_with_guidance("hi", DialogueState())
    assert res["status"] == "clarify"
    assert res["slot_candidates"]["phase"] == ["实施"]
    # 兜底保证项目候选存在
    assert "project_name" in res["slot_candidates"]


def test_semantic_similarity_blocks_repeated():
    sources = [{"page_type": ["features"], "similarity": 0.9}]
    qa = DummyQAEngine({"status": "success", "sources": sources, "answer": "ok"})
    templates = {"follow_ups_by_module": {"features": ["了解部署方式吗？", "了解部署方式吗", "新的建议"], "default": ["d1"]}}
    state = DialogueState(
        recent_suggestions=["了解部署方式吗？"],
        suggestion_cooldown={"了解部署方式吗？": 2},
        slots={"project_name": "ChatBI"},
    )
    orch = DialogueOrchestrator(qa_engine=qa, templates=templates, gap_threshold=0.1)
    res = orch.answer_with_guidance("问句", state)
    assert "了解部署方式吗" not in res["suggestions"]  # 语义重复被阻断
    assert "新的建议" in res["suggestions"]
    assert state.repeat_blocked_count >= 1
