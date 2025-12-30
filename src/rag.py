import json
from typing import Any, Dict, List, Optional, Tuple

from src.models import PageSummary, ProjectProfile


def prepare_slide_embedding(project_name: str, summary: PageSummary) -> Dict[str, Any]:
    """
    Convert a PageSummary into a document ready for vector embedding.
    Level: Detail (Slide)
    """
    # 1. Construct Semantic Text (Flattened for Embedding)
    text_content = f"项目: {project_name}\n"
    if summary.title:
        text_content += f"页面标题: {summary.title}\n"
    if summary.image_caption:
        text_content += f"视觉描述: {summary.image_caption}\n"
    if summary.one_liner:
        text_content += f"核心总结: {summary.one_liner}\n"
    if summary.signals:
        text_content += f"类型: {', '.join(summary.signals)}\n"
    if summary.bullets:
        text_content += "关键点:\n"
        for bullet in summary.bullets:
            text_content += f"- {bullet}\n"
    if summary.details:
        text_content += f"详情: {summary.details}\n"
    # Inject keywords to boost relevance
    if summary.entities:
        text_content += f"关键词: {', '.join(summary.entities)}\n"

    # 2. Construct Metadata (For Filtering)
    metadata = {
        "project_name": project_name,
        "source": project_name, # Alias for consistency
        "slide_no": summary.slide_no,
        "page_type": summary.signals,
        "entities": summary.entities,
        "confidence": summary.confidence,
        "level": "slide"
    }

    # 3. Return Document Object
    return {
        "id": f"{project_name}_slide_{summary.slide_no:03d}",
        "text": text_content,
        "metadata": metadata,
        "original_json": json.dumps(summary.model_dump(), ensure_ascii=False)
    }


def prepare_project_embedding(project_name: str, profile: ProjectProfile) -> Dict[str, Any]:
    """
    Convert a ProjectProfile into a document ready for vector embedding.
    Level: Overview (Project)
    """
    # 1. Construct Semantic Text
    # We select high-level fields that describe the "What" and "Why" of the project.
    text_content = f"项目综述: {project_name}\n"

    if profile.positioning:
        text_content += f"定位: {profile.positioning}\n"

    if profile.core_value:
        text_content += f"核心价值: {profile.core_value}\n"
    if profile.target_users:
        text_content += f"目标用户: {', '.join(profile.target_users)}\n"
    if profile.core_capabilities:
        text_content += f"核心能力: {', '.join(profile.core_capabilities)}\n"
    if profile.differentiators:
        text_content += f"差异化优势: {', '.join(profile.differentiators)}\n"
    if profile.architecture:
        text_content += f"技术架构: {profile.architecture}\n"
    if profile.deployment:
        text_content += f"部署方式: {profile.deployment}\n"
    if profile.integrations:
        text_content += f"集成: {', '.join(profile.integrations)}\n"
    if profile.cases:
        text_content += f"案例: {', '.join(profile.cases)}\n"
    if profile.risks_and_limits:
        text_content += f"风险与限制: {', '.join(profile.risks_and_limits)}\n"
    if profile.open_questions:
        text_content += f"未决问题: {', '.join(profile.open_questions)}\n"

    # 2. Construct Metadata
    metadata = {
        "project_name": project_name,
        "source": project_name,
        "slide_no": 0, # Virtual slide 0 for overview
        "page_type": ["overview", "profile"],
        "level": "project"
    }

    # 3. Return Document Object
    return {
        "id": f"{project_name}_overview",
        "text": text_content,
        "metadata": metadata,
        "original_json": json.dumps(profile.model_dump(), ensure_ascii=False)
    }


def _looks_like_embedded_json(text: str) -> bool:
    text = text.strip()
    if not text.startswith(("{", "[")):
        return False
    json_keys = ["slide_no", "title", "one_liner", "bullets", "details"]
    return any(key in text for key in json_keys)


def _unpack_json_blob(text: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            parsed = parsed[0]
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks that some models prepend."""
    start_tag, end_tag = "<think>", "</think>"
    while True:
        start = text.find(start_tag)
        if start == -1:
            break
        end = text.find(end_tag, start + len(start_tag))
        if end == -1:
            # No closing tag; drop from start tag onward
            text = text[:start]
            break
        text = text[:start] + text[end + len(end_tag) :]
    return text.strip()


def _extract_embedded_json(text: str) -> Optional[Dict[str, Any] | List[Any]]:
    """Find first '{' or '[' in text (after stripping <think>) and try to json.loads from there."""
    cleaned = _strip_think_blocks(text)
    for ch in ("{", "["):
        idx = cleaned.find(ch)
        if idx != -1:
            candidate = cleaned[idx:]
            try:
                return json.loads(candidate)
            except Exception:
                continue
    return None


def clean_summary_for_embedding(summary: PageSummary) -> Tuple[PageSummary, List[str]]:
    """
    Unnests suspicious JSON-like details and flags noisy bullets before embedding.
    Returns a possibly updated summary and a list of issue messages.
    """
    issues: List[str] = []
    new_summary = summary

    # 1) details: try strict head, then embedded JSON after stripping think
    if isinstance(summary.details, str):
        looks_json = _looks_like_embedded_json(summary.details) or ("{" in summary.details or "[" in summary.details)
        if looks_json:
            unpacked = None
            if _looks_like_embedded_json(summary.details):
                unpacked = _unpack_json_blob(summary.details)
            if not unpacked:
                embedded = _extract_embedded_json(summary.details)
                if isinstance(embedded, dict):
                    unpacked = embedded

            if unpacked:
                new_summary = summary.model_copy(
                    update={
                        "bullets": unpacked.get("bullets") or summary.bullets,
                        "details": unpacked.get("details") or summary.details,
                    }
                )
            else:
                issues.append("detail_unpack_failed")

    # 2) bullets: attempt to unpack if a bullet carries JSON; otherwise flag
    new_bullets: List[str] = []
    bullets_flagged = False
    bullets_unpacked = False
    for b in new_summary.bullets:
        if isinstance(b, str) and ("{" in b or "[" in b):
            parsed = _extract_embedded_json(b)
            if isinstance(parsed, dict) and parsed.get("bullets"):
                new_bullets.extend(parsed["bullets"])
                bullets_unpacked = True
                continue
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                new_bullets.extend(parsed)
                bullets_unpacked = True
                continue
            bullets_flagged = True
            new_bullets.append(b)
        else:
            new_bullets.append(b)

    if bullets_unpacked:
        new_summary = new_summary.model_copy(update={"bullets": new_bullets})
    if bullets_flagged:
        issues.append("bullets_look_like_json")

    return new_summary, issues
