from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SlideText(BaseModel):
    slide_no: int
    title: Optional[str] = None
    text_content: str = ""
    notes: Optional[str] = None


class PageSummary(BaseModel):
    slide_no: int
    title: Optional[str] = None
    one_liner: str = ""
    bullets: List[str] = Field(default_factory=list)
    image_caption: Optional[str] = None
    details: Optional[str] = None
    entities: List[str] = Field(default_factory=list)
    signals: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    confidence: float = 0.0


class ProjectProfile(BaseModel):
    project_name: Optional[str] = None
    positioning: Optional[str] = None
    target_users: List[str] = Field(default_factory=list)
    core_value: Optional[str] = None
    core_capabilities: List[str] = Field(default_factory=list)
    architecture: Optional[str] = None
    deployment: Optional[str] = None
    integrations: List[str] = Field(default_factory=list)
    differentiators: List[str] = Field(default_factory=list)
    cases: List[str] = Field(default_factory=list)
    risks_and_limits: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    evidence_map: Dict[str, List[int]] = Field(default_factory=dict)


class Manifest(BaseModel):
    input_file: str
    file_hash: str
    timestamp: str
    page_count: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    duration_seconds: float
    output_dir: str
    provider: str
    model: str
    page_summaries: int
    rag_documents: int = 0
