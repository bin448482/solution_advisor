"""
Data models for RAG v2 (QA-pair approach)
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Category(str, Enum):
    """8 standard categories for content classification."""
    POSITIONING = "positioning"      # 产品定位、核心价值
    FEATURES = "features"            # 功能特性、能力
    ARCHITECTURE = "architecture"    # 技术架构、系统设计
    DEPLOYMENT = "deployment"        # 部署方式、交付模式
    INTEGRATION = "integration"      # 集成对接、API
    CASES = "cases"                  # 客户案例、POC
    COMPARISON = "comparison"        # 竞品对比、差异化
    ROADMAP = "roadmap"             # 产品规划、未来方向


# Category name mapping (Chinese)
CATEGORY_NAMES = {
    Category.POSITIONING: "产品定位",
    Category.FEATURES: "功能特性",
    Category.ARCHITECTURE: "技术架构",
    Category.DEPLOYMENT: "部署运维",
    Category.INTEGRATION: "集成对接",
    Category.CASES: "客户案例",
    Category.COMPARISON: "竞品对比",
    Category.ROADMAP: "产品规划",
}


def get_category_name(category: Category) -> str:
    """Get Chinese name for a category."""
    return CATEGORY_NAMES.get(category, category.value)


class QAPair(BaseModel):
    """Single question-answer pair extracted from a slide."""
    question: str = Field(..., min_length=5, max_length=200, description="Main question")
    answer: str = Field(..., min_length=10, description="Complete answer")
    alt_questions: List[str] = Field(default_factory=list, max_length=3, description="Alternative phrasings")
    category: Category = Field(..., description="Content category")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    source_slide: int = Field(..., ge=1, description="Source slide number")
    keywords: List[str] = Field(default_factory=list, max_length=8, description="Key terms")


class ChunkMetadata(BaseModel):
    """Standardized metadata schema for all chunk types."""
    project_name: str
    chunk_type: str  # qa_pair | metrics | overview | category_summary | topic | step
    level: str  # slide | project | category
    summary: Optional[str] = None
    qa_examples: Optional[List[Dict[str, Any]]] = None

    # Confidence/score
    confidence: Optional[float] = None

    # Optional slide reference (for backward compatibility)
    slide_no: Optional[int] = None

    # QA-specific fields
    qa_question: Optional[str] = None
    alt_questions: Optional[List[str]] = None
    answer: Optional[str] = None

    # Metrics-specific fields
    metric_items: Optional[List[Dict[str, Any]]] = None

    # Classification
    category_id: Optional[str] = None
    category_name: Optional[str] = None

    # Traceability
    source_slide_refs: List[int] = Field(default_factory=list)
    source_file: Optional[str] = None          # 单来源文件，如 page_summaries/003.json
    source_files: Optional[List[str]] = None   # 多来源文件（聚合类 chunk）

    # Legacy fields (kept for retrieval heuristics)
    page_type: Optional[List[str]] = None
    entities: Optional[List[str]] = None


class ChunkDocument(BaseModel):
    """Unified chunk document for vector DB insertion."""
    id: str = Field(..., description="Unique document ID")
    text: str = Field(..., description="Semantic text for embedding")
    metadata: Dict[str, Any] = Field(..., description="Enhanced metadata")
    original_json: Optional[str] = Field(None, description="Original data as JSON string")
