import json
from typing import Dict, List

from src.models import PageSummary, ProjectProfile
from src.prompts import get_project_profile_prompt
from src.summarizer.llm_client import LLMClient

PROFILE_PROMPT = get_project_profile_prompt()


class ProfileGenerator:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def generate(self, page_summaries: List[PageSummary]) -> ProjectProfile:
        if not page_summaries:
            return ProjectProfile()

        if self.client.is_mock:
            return self._mock_profile(page_summaries)

        prompt = self._build_prompt(page_summaries)
        raw = self.client.generate(prompt)
        data = self._parse_json(raw)
        return ProjectProfile(**data)

    def _build_prompt(self, page_summaries: List[PageSummary]) -> str:
        lines = []
        for ps in page_summaries:
            bullets = "; ".join(ps.bullets) if ps.bullets else ps.one_liner
            lines.append(f"第{ps.slide_no}页【{ps.title or '无标题'}】: {ps.one_liner}; 关键点: {bullets}")
        joined = "\n".join(lines)
        return f"{PROFILE_PROMPT}\n以下是单页总结：\n{joined}\n只输出 JSON。"

    def _parse_json(self, raw: str) -> Dict:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {}

    def _mock_profile(self, page_summaries: List[PageSummary]) -> ProjectProfile:
        bullets = [ps.one_liner for ps in page_summaries if ps.one_liner]
        evidence_map = {ps.title or f"slide_{ps.slide_no}": [ps.slide_no] for ps in page_summaries}
        return ProjectProfile(
            project_name=page_summaries[0].title or "未命名项目",
            positioning=bullets[0] if bullets else None,
            target_users=[],
            core_value=bullets[1] if len(bullets) > 1 else None,
            core_capabilities=[],
            architecture=None,
            deployment=None,
            integrations=[],
            differentiators=[],
            cases=[],
            risks_and_limits=[],
            open_questions=[],
            evidence_map=evidence_map,
        )
