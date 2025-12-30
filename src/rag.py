from typing import Any, Dict, List

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
        "original_json": summary.model_dump()
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
        text_content += f"目标用户: {', '.join(profile.profile.target_users)}\n"
        
    if profile.core_capabilities:
        text_content += f"核心能力: {', '.join(profile.profile.core_capabilities)}\n"
        
    if profile.differentiators:
        text_content += f"差异化优势: {', '.join(profile.profile.differentiators)}\n"

    if profile.risks_and_limits:
        text_content += f"风险与限制: {', '.join(profile.profile.risks_and_limits)}\n"

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
        "original_json": profile.model_dump()
    }
