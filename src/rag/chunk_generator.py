"""
Multi-Type Chunk Generator

Generates various chunk types from PageSummary and ProjectProfile:
- qa_pair: Question-answer pairs (primary)
- category_summary: Aggregated summary per Category
- topic: Thematic content blocks (optional / legacy)
- step: Sequential/process steps (optional / legacy)
- metrics: Performance/data metrics (optional)
- overview: Project-level summary
"""
import json
from typing import Any, Dict, List, Sequence

from src.models import PageSummary, ProjectProfile
from src.rag.models import QAPair, ChunkDocument, ChunkMetadata, Category, get_category_name
from src.rag.legacy import _classify_page_types


class ChunkGenerator:
    """Generates multiple chunk types from summaries and profiles."""

    def generate_qa_chunks(
        self,
        qa_pairs: List[QAPair],
        project_name: str
    ) -> List[ChunkDocument]:
        """
        Generate QA-pair chunks (primary chunk type).

        Args:
            qa_pairs: List of QAPair objects
            project_name: Project name

        Returns:
            List of ChunkDocument objects
        """
        chunks: List[ChunkDocument] = []

        for idx, qa in enumerate(qa_pairs, 1):
            chunk_id = f"{project_name}_slide_{qa.source_slide:03d}_qa_{idx:03d}"
            source_file = f"page_summaries/{qa.source_slide:03d}.json"

            # Semantic text for embedding
            text = f"项目: {project_name}\n"
            text += f"问题: {qa.question}\n"
            if qa.alt_questions:
                text += f"相关问法: {', '.join(qa.alt_questions)}\n"
            text += f"答案: {qa.answer}\n"
            if qa.keywords:
                text += f"关键词: {', '.join(qa.keywords)}\n"

            # Metadata
            metadata = ChunkMetadata(
                project_name=project_name,
                chunk_type="qa_pair",
                level="slide",
                confidence=qa.confidence,
                slide_no=qa.source_slide,
                qa_question=qa.question,
                alt_questions=qa.alt_questions,
                answer=qa.answer,
                category_id=qa.category.value,
                category_name=get_category_name(qa.category),
                entities=qa.keywords,
                source_slide_refs=[qa.source_slide],
                source_file=source_file,
            )

            chunks.append(ChunkDocument(
                id=chunk_id,
                text=text,
                metadata=metadata.model_dump(),
                original_json=json.dumps(
                    {"source_file": source_file, "slide_no": qa.source_slide},
                    ensure_ascii=False,
                ),
            ))

        return chunks

    def generate_category_summary_chunks(
        self,
        qa_pairs: Sequence[QAPair],
        project_name: str,
        *,
        max_examples: int = 5
    ) -> List[ChunkDocument]:
        """
        Aggregate QA 对按 Category 形成摘要 chunk。

        Args:
            qa_pairs: 全量 QA 对列表（已含 category）
            project_name: 项目名
            max_examples: 每个类别最多纳入多少条示例问答

        Returns:
            List[ChunkDocument]
        """
        if not qa_pairs:
            return []

        chunks: List[ChunkDocument] = []
        category_map: Dict[Category, List[QAPair]] = {}
        for qa in qa_pairs:
            category_map.setdefault(qa.category, []).append(qa)

        for category, items in category_map.items():
            if not items:
                continue

            # 优先高置信度，截断示例数量与答案长度，避免超长文本
            items_sorted = sorted(items, key=lambda q: q.confidence, reverse=True)
            examples = items_sorted[:max_examples]

            text_lines = [
                f"项目: {project_name}",
                f"类别: {get_category_name(category)} ({category.value})",
                f"该类别共 {len(items)} 个问答，以下为精选 {len(examples)} 条：",
            ]
            for qa in examples:
                answer_snippet = qa.answer
                if len(answer_snippet) > 200:
                    answer_snippet = answer_snippet[:197] + "..."
                alt = f"  相关问法: {', '.join(qa.alt_questions)}" if qa.alt_questions else ""
                text_lines.append(f"- 问题: {qa.question}")
                text_lines.append(f"  答案: {answer_snippet}")
                if alt:
                    text_lines.append(alt)

            text = "\n".join(text_lines) + "\n"

            source_slides = sorted({qa.source_slide for qa in items})
            source_files = sorted({f"page_summaries/{s:03d}.json" for s in source_slides})
            chunk_id = f"{project_name}_category_{category.value}"

            metadata = ChunkMetadata(
                project_name=project_name,
                chunk_type="category_summary",
                level="category",
                confidence=self._avg_confidence(items),
                category_id=category.value,
                category_name=get_category_name(category),
                source_slide_refs=source_slides,
                source_files=source_files,
            )

            chunks.append(ChunkDocument(
                id=chunk_id,
                text=text,
                metadata=metadata.model_dump(),
                original_json=json.dumps(
                    {
                        "source_files": source_files,
                        "category": category.value,
                        "qa_count": len(items),
                    },
                    ensure_ascii=False,
                ),
            ))

        return chunks

    def generate_topic_chunks(
        self,
        summary: PageSummary,
        project_name: str
    ) -> List[ChunkDocument]:
        """
        Generate topic chunks for slides with clear thematic structure.

        Args:
            summary: PageSummary object
            project_name: Project name

        Returns:
            List of ChunkDocument objects (0-3 chunks)
        """
        # Only generate if slide has substantial content
        if not summary.bullets or len(summary.bullets) < 3:
            return []

        chunks: List[ChunkDocument] = []
        chunk_id = f"{project_name}_slide_{summary.slide_no:03d}_topic_001"
        source_file = f"page_summaries/{summary.slide_no:03d}.json"

        # Semantic text
        text = f"项目: {project_name}\n"
        if summary.title:
            text += f"主题: {summary.title}\n"
        if summary.one_liner:
            text += f"概述: {summary.one_liner}\n"
        text += "要点:\n"
        for bullet in summary.bullets:
            text += f"- {bullet}\n"
        if summary.details:
            text += f"详情: {summary.details}\n"

        # Metadata
        page_types = _classify_page_types(summary)
        metadata = ChunkMetadata(
            project_name=project_name,
            chunk_type="topic",
            level="slide",
            confidence=summary.confidence,
            slide_no=summary.slide_no,
            page_type=page_types,
            entities=summary.entities,
            source_slide_refs=[summary.slide_no],
            source_file=source_file,
        )

        chunks.append(ChunkDocument(
            id=chunk_id,
            text=text,
            metadata=metadata.model_dump(),
            original_json=json.dumps({"source_file": source_file, "slide_no": summary.slide_no}, ensure_ascii=False)
        ))

        return chunks

    def generate_step_chunks(
        self,
        summary: PageSummary,
        project_name: str
    ) -> List[ChunkDocument]:
        """
        Generate step chunks for process/workflow slides.

        Args:
            summary: PageSummary object
            project_name: Project name

        Returns:
            List of ChunkDocument objects (0-5 chunks)
        """
        # Detect sequential content
        if not self._has_sequential_content(summary):
            return []

        chunks: List[ChunkDocument] = []

        # Generate one chunk per step (from bullets)
        for idx, bullet in enumerate(summary.bullets, 1):
            chunk_id = f"{project_name}_slide_{summary.slide_no:03d}_step_{idx:03d}"
            source_file = f"page_summaries/{summary.slide_no:03d}.json"

            # Semantic text
            text = f"项目: {project_name}\n"
            if summary.title:
                text += f"流程: {summary.title}\n"
            text += f"步骤 {idx}: {bullet}\n"
            if summary.details:
                text += f"说明: {summary.details}\n"

            # Metadata
            page_types = _classify_page_types(summary)
            metadata = ChunkMetadata(
                project_name=project_name,
                chunk_type="step",
                level="slide",
                confidence=summary.confidence,
                slide_no=summary.slide_no,
                page_type=page_types,
                entities=summary.entities,
                source_slide_refs=[summary.slide_no],
                source_file=source_file,
            )

            chunks.append(ChunkDocument(
                id=chunk_id,
                text=text,
                metadata=metadata.model_dump(),
                original_json=json.dumps({"source_file": source_file, "slide_no": summary.slide_no}, ensure_ascii=False)
            ))

        return chunks

    def generate_metrics_chunks(
        self,
        summary: PageSummary,
        project_name: str
    ) -> List[ChunkDocument]:
        """
        Generate metrics chunks for performance/data slides.

        Args:
            summary: PageSummary object
            project_name: Project name

        Returns:
            List of ChunkDocument objects (0-2 chunks)
        """
        # Detect metrics content
        if not self._has_metrics(summary):
            return []

        chunks: List[ChunkDocument] = []
        chunk_id = f"{project_name}_slide_{summary.slide_no:03d}_metrics_001"
        source_file = f"page_summaries/{summary.slide_no:03d}.json"

        # Semantic text
        text = f"项目: {project_name}\n"
        if summary.title:
            text += f"指标: {summary.title}\n"
        if summary.one_liner:
            text += f"概述: {summary.one_liner}\n"
        if summary.bullets:
            text += "数据:\n"
            for bullet in summary.bullets:
                text += f"- {bullet}\n"
        if summary.details:
            text += f"说明: {summary.details}\n"

        # Metadata
        page_types = _classify_page_types(summary)
        metadata = ChunkMetadata(
            project_name=project_name,
            chunk_type="metrics",
            level="slide",
            confidence=summary.confidence,
            slide_no=summary.slide_no,
            page_type=page_types,
            entities=summary.entities,
            source_slide_refs=[summary.slide_no],
            source_file=source_file,
        )

        chunks.append(ChunkDocument(
            id=chunk_id,
            text=text,
            metadata=metadata.model_dump(),
            original_json=json.dumps({"source_file": source_file, "slide_no": summary.slide_no}, ensure_ascii=False)
        ))

        return chunks

    def generate_overview_chunk(
        self,
        profile: ProjectProfile,
        project_name: str
    ) -> ChunkDocument:
        """
        Generate project-level overview chunk.

        Args:
            profile: ProjectProfile object
            project_name: Project name

        Returns:
            ChunkDocument object
        """
        # Semantic text (similar to legacy prepare_project_embedding)
        text = f"项目综述: {project_name}\n"

        if profile.positioning:
            text += f"定位: {profile.positioning}\n"
        if profile.core_value:
            text += f"核心价值: {profile.core_value}\n"
        if profile.target_users:
            text += f"目标用户: {', '.join(profile.target_users)}\n"
        if profile.core_capabilities:
            text += f"核心能力: {', '.join(profile.core_capabilities)}\n"
        if profile.differentiators:
            text += f"差异化优势: {', '.join(profile.differentiators)}\n"
        if profile.architecture:
            text += f"技术架构: {profile.architecture}\n"
        if profile.deployment:
            text += f"部署方式: {profile.deployment}\n"
        if profile.integrations:
            text += f"集成: {', '.join(profile.integrations)}\n"
        if profile.cases:
            text += f"案例: {', '.join(profile.cases)}\n"

        # Metadata
        metadata = ChunkMetadata(
            project_name=project_name,
            chunk_type="overview",
            level="project",
            confidence=1.0,
            page_type=["overview", "profile"],
            source_slide_refs=[],
            source_file="doc_summary/project_profile.json",
        )

        return ChunkDocument(
            id=f"{project_name}_overview",
            text=text,
            metadata=metadata.model_dump(),
            original_json=json.dumps({"source_file": "doc_summary/project_profile.json"}, ensure_ascii=False)
        )

    def decide_chunk_types(self, summary: PageSummary) -> List[str]:
        """
        Decide which chunk types to generate for a slide.

        Args:
            summary: PageSummary object

        Returns:
            List of chunk type names
        """
        types = ["qa_pair"]  # Always generate QA pairs

        # Topic chunks: slides with clear thematic structure
        if self._has_clear_topics(summary):
            types.append("topic")

        # Step chunks: process/workflow slides
        if self._has_sequential_content(summary):
            types.append("step")

        # Metrics chunks: performance/data slides
        if self._has_metrics(summary):
            types.append("metrics")

        return types

    def _has_clear_topics(self, summary: PageSummary) -> bool:
        """Check if slide has clear thematic structure."""
        return (
            summary.bullets and len(summary.bullets) >= 3
            and summary.details and len(summary.details) > 50
        )

    def _has_sequential_content(self, summary: PageSummary) -> bool:
        """Check if slide has sequential/process content."""
        text_fields = [summary.title or "", summary.one_liner or ""]
        text_fields.extend(summary.bullets or [])
        text_fields.extend(summary.signals or [])

        joined = " ".join(text_fields).lower()

        # Keywords indicating sequential content
        sequential_keywords = [
            "步骤", "流程", "阶段", "过程", "step", "phase", "stage", "process",
            "第一", "第二", "第三", "首先", "然后", "最后", "接着"
        ]

        return any(kw in joined for kw in sequential_keywords)

    def _has_metrics(self, summary: PageSummary) -> bool:
        """Check if slide has performance/data metrics."""
        text_fields = [summary.title or "", summary.one_liner or ""]
        text_fields.extend(summary.bullets or [])
        text_fields.extend(summary.signals or [])
        text_fields.extend(summary.entities or [])

        joined = " ".join(text_fields).lower()

        # Keywords indicating metrics
        metrics_keywords = [
            "性能", "指标", "数据", "qps", "tps", "延迟", "latency",
            "吞吐", "响应时间", "压测", "benchmark", "提升", "%", "倍",
            "ms", "秒", "分钟", "小时"
        ]

        return any(kw in joined for kw in metrics_keywords)

    @staticmethod
    def _avg_confidence(items: Sequence[QAPair]) -> float:
        if not items:
            return 0.0
        return round(sum(i.confidence for i in items) / len(items), 4)
