import json
from pathlib import Path
from typing import Dict, List, Optional

from src.models import PageSummary, SlideText
from src.summarizer.llm_client import LLMClient

PAGE_PROMPT = """
你是产品项目分析助手，请根据幻灯片文本（和可见图片）生成结构化总结，输出 JSON，字段：
- slide_no (int)
- title (string)
- one_liner (string)：一句话中文总结
- bullets (string[])：3-6 条关键信息
- image_caption (string)：基于视觉的简短描述（无结构化失败时可为空）
- details (string)
- entities (string[])：提到的机构、产品、角色
- signals (string[])：发现的信号/指标
- evidence (string[])：证据或来源描述
- confidence (float 0-1)

请直接输出 JSON，不要添加额外说明。
"""


class PageSummarizer:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def summarize(self, slide: SlideText, image_path: Optional[Path]) -> PageSummary:
        if self.client.is_mock:
            return self._mock_summary(slide)

        prompt = self._build_prompt(slide, bool(image_path))
        raw = self.client.generate(prompt, image_path=image_path)
        data = self._parse_json(raw, slide)
        return PageSummary(**data)

    def _build_prompt(self, slide: SlideText, has_image: bool) -> str:
        text_block = f"标题: {slide.title or ''}\n正文:\n{slide.text_content}"
        if slide.notes:
            text_block += f"\n讲稿/备注:\n{slide.notes}"
        image_hint = "已提供幻灯片图片，可结合视觉内容。" if has_image else "未提供图片，仅使用文本。"
        return f"{PAGE_PROMPT}\n{image_hint}\n文本内容：\n{text_block}\n只输出 JSON。"

    def _parse_json(self, raw: str, slide: SlideText) -> Dict:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                parsed = parsed[0]
            if isinstance(parsed, dict):
                return self._fill_defaults(parsed, slide)
        except json.JSONDecodeError:
            pass
        # Fallback if model returns non-JSON
        return self._fill_defaults({}, slide, fallback_text=raw)

    def _fill_defaults(self, data: Dict, slide: SlideText, fallback_text: Optional[str] = None) -> Dict:
        bullets: List[str] = data.get("bullets") or []
        if fallback_text and not bullets:
            bullets = [line.strip() for line in fallback_text.splitlines() if line.strip()][:5]
        image_caption = data.get("image_caption")
        return {
            "slide_no": data.get("slide_no", slide.slide_no),
            "title": data.get("title", slide.title),
            "one_liner": data.get("one_liner") or (slide.text_content.split("\n")[0][:80] if slide.text_content else "暂无摘要"),
            "bullets": bullets,
            "image_caption": image_caption,
            "details": data.get("details") or fallback_text,
            "entities": data.get("entities") or [],
            "signals": data.get("signals") or [],
            "evidence": data.get("evidence") or [],
            "confidence": float(data.get("confidence") or 0.3),
        }

    def _mock_summary(self, slide: SlideText) -> PageSummary:
        text_lines = [line.strip() for line in slide.text_content.splitlines() if line.strip()]
        bullets = text_lines[:4] if text_lines else []
        one_liner = slide.title or (text_lines[0] if text_lines else "未找到内容")
        return PageSummary(
            slide_no=slide.slide_no,
            title=slide.title,
            one_liner=one_liner,
            bullets=bullets,
            image_caption=one_liner,
            details=None,
            entities=[],
            signals=[],
            evidence=[],
            confidence=0.2,
        )
