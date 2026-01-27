import json
from pathlib import Path
from typing import Dict, List, Optional

from src.models import PageSummary, SlideText
from src.prompts import get_page_summary_prompt
from src.summarizer.llm_client import LLMClient

PAGE_PROMPT = get_page_summary_prompt()


class PageSummarizer:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def summarize(self, slide: SlideText | None, image_path: Optional[Path], slide_no: Optional[int] = None) -> PageSummary:
        slide_no = self._resolve_slide_no(slide, image_path, slide_no)
        if self.client.is_mock:
            return self._mock_summary(slide, slide_no)

        prompt = self._build_prompt(slide, bool(image_path))
        raw = self.client.generate(prompt, image_path=image_path)
        data = self._parse_json(raw, slide, slide_no)
        return PageSummary(**data)

    def _build_prompt(self, slide: SlideText | None, has_image: bool) -> str:
        if slide is None:
            image_hint = "仅提供图片，请只根据视觉内容进行总结；如不确定请降低置信度。"
            return f"{PAGE_PROMPT}\n{image_hint}\n文本内容：\n(无)\n只输出 JSON。"

        text_block = f"标题: {slide.title or ''}\n正文:\n{slide.text_content}"
        if slide.notes:
            text_block += f"\n讲稿/备注:\n{slide.notes}"
        image_hint = "已提供幻灯片图片，可结合视觉内容。" if has_image else "未提供图片，仅使用文本。"
        return f"{PAGE_PROMPT}\n{image_hint}\n文本内容：\n{text_block}\n只输出 JSON。"

    def _parse_json(self, raw: str, slide: SlideText | None, slide_no: int) -> Dict:
        error_msg = ""
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                parsed = parsed[0]
            if isinstance(parsed, dict):
                return self._fill_defaults(parsed, slide, slide_no)
        except json.JSONDecodeError as e:
            error_msg = f"JSON Parse Error: {str(e)}"
        
        # Fallback if model returns non-JSON
        return self._fill_defaults({}, slide, slide_no, fallback_text=raw, error_msg=error_msg)

    def _fill_defaults(
        self, data: Dict, slide: SlideText | None, slide_no: int, fallback_text: Optional[str] = None, error_msg: str = ""
    ) -> Dict:
        bullets: List[str] = data.get("bullets") or []
        if fallback_text and not bullets:
            bullets = [line.strip() for line in fallback_text.splitlines() if line.strip()][:5]
        
        details = data.get("details")
        if not details and fallback_text:
            details = fallback_text
        if error_msg:
            details = f"[SYSTEM ERROR] {error_msg}\n\n[RAW OUTPUT]\n{details or ''}"

        image_caption = data.get("image_caption")
        title = data.get("title", slide.title if slide else None)
        text_content = slide.text_content if slide else ""
        one_liner = data.get("one_liner") or (text_content.split("\n")[0][:80] if text_content else "图片内容摘要")
        return {
            # 强制使用管线内的页码，避免模型输出重复或错误的 slide_no
            "slide_no": slide_no,
            "title": title,
            "one_liner": one_liner,
            "bullets": bullets,
            "image_caption": image_caption,
            "details": data.get("details") or fallback_text,
            "entities": data.get("entities") or [],
            "signals": data.get("signals") or [],
            "evidence": data.get("evidence") or [],
            "confidence": float(data.get("confidence") or 0.3),
        }

    def _mock_summary(self, slide: SlideText | None, slide_no: int) -> PageSummary:
        if slide is None:
            return PageSummary(
                slide_no=slide_no,
                title=None,
                one_liner="图片内容摘要",
                bullets=[],
                image_caption="图片内容摘要",
                details=None,
                entities=[],
                signals=[],
                evidence=[],
                confidence=0.2,
            )

        text_lines = [line.strip() for line in slide.text_content.splitlines() if line.strip()]
        bullets = text_lines[:4] if text_lines else []
        one_liner = slide.title or (text_lines[0] if text_lines else "未找到内容")
        return PageSummary(
            slide_no=slide_no,
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

    @staticmethod
    def _resolve_slide_no(slide: SlideText | None, image_path: Optional[Path], slide_no: Optional[int]) -> int:
        if slide_no is not None:
            return slide_no
        if slide is not None:
            return slide.slide_no
        if image_path is not None:
            try:
                return int(image_path.stem)
            except ValueError:
                return 0
        return 0
