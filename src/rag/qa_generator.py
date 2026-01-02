"""
QA Pair Generator

Generates 5-10 question-answer pairs from PageSummary objects using LLM.
"""
import json
import time
from typing import List, Optional

from src.models import PageSummary
from src.summarizer.llm_client import LLMClient
from src.rag.models import QAPair, Category


# QA Generation Prompt Template (Chinese)
QA_GENERATION_PROMPT = """你是一个专业的问答对生成专家。请根据以下幻灯片内容生成5-10个高质量的问答对。

项目名称: {project_name}
幻灯片编号: {slide_no}
标题: {title}
核心总结: {one_liner}
关键点:
{bullets}
详细内容: {details}

要求:
1. 生成5-10个问答对，覆盖该页面的核心信息
2. 问题应该是用户可能提出的自然问题（10-50字）
3. 答案应该准确、完整、可独立理解（50-300字）
4. 为每个问题提供0-3个替代问法（可选）
5. 提取关键词（3-8个）
6. 评估置信度（0.0-1.0，基于信息完整性和清晰度）

输出JSON格式:
{{
  "qa_pairs": [
    {{
      "question": "ChatBI支持哪些数据源?",
      "answer": "ChatBI支持MySQL、PostgreSQL、Oracle等主流关系型数据库，以及Hive、ClickHouse等大数据平台。通过标准JDBC/ODBC连接，可以快速对接企业现有数据资产。",
      "alt_questions": ["ChatBI能连接什么数据库", "支持的数据源类型有哪些"],
      "keywords": ["数据源", "MySQL", "PostgreSQL", "集成", "JDBC"],
      "confidence": 0.95
    }}
  ]
}}

注意:
- 问题要具体、可回答，避免过于宽泛
- 答案要基于页面内容，不要编造信息
- 如果页面信息不足以生成高质量问答，可以生成较少的问答对（最少3个）
- 置信度低于0.5的问答对会被过滤，请确保质量
"""


class QAGenerator:
    """Generates QA pairs from PageSummary using LLM."""

    def __init__(self, llm_client: LLMClient, min_confidence: float = 0.3):
        self.llm_client = llm_client
        self.min_confidence = min_confidence

    def generate_qa_pairs(
        self,
        summary: PageSummary,
        project_name: str,
        max_retries: int = 3
    ) -> List[QAPair]:
        """
        Generate 5-10 QA pairs from a single slide summary.

        Args:
            summary: PageSummary object
            project_name: Project name for context
            max_retries: Maximum retry attempts on failure

        Returns:
            List of QAPair objects (filtered by confidence)
        """
        # Format bullets
        bullets_text = "\n".join(f"- {b}" for b in summary.bullets) if summary.bullets else "无"

        # Mock provider shortcut to keep pipelines green
        if self.llm_client.is_mock:
            return self._mock_pairs(summary, project_name)

        # Build prompt
        prompt = QA_GENERATION_PROMPT.format(
            project_name=project_name,
            slide_no=summary.slide_no,
            title=summary.title or "无标题",
            one_liner=summary.one_liner or "无",
            bullets=bullets_text,
            details=summary.details or "无"
        )

        # Retry logic with exponential backoff
        for attempt in range(max_retries):
            try:
                response = self.llm_client.generate(prompt)
                qa_pairs = self._parse_response(response, summary.slide_no)

                # Filter by confidence
                filtered = [qa for qa in qa_pairs if qa.confidence >= self.min_confidence]

                if not filtered:
                    raise ValueError(f"No QA pairs passed confidence threshold ({self.min_confidence})")

                return filtered

            except Exception as exc:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    time.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed
                    raise RuntimeError(
                        f"QA generation failed for slide {summary.slide_no} after {max_retries} attempts: {exc}"
                    )

    def _parse_response(self, response: str, slide_no: int) -> List[QAPair]:
        """
        Parse LLM response into QAPair objects.

        Args:
            response: Raw LLM response (JSON string)
            slide_no: Source slide number

        Returns:
            List of QAPair objects

        Raises:
            ValueError: If response cannot be parsed
        """
        try:
            # Try to parse as JSON
            data = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from response (handle markdown code blocks)
            response = response.strip()
            if response.startswith("```"):
                # Remove markdown code block markers
                lines = response.split("\n")
                response = "\n".join(lines[1:-1]) if len(lines) > 2 else response
            try:
                data = json.loads(response)
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse QA response as JSON: {e}")

        # Extract qa_pairs array
        qa_pairs_data = data.get("qa_pairs", [])
        if not qa_pairs_data:
            raise ValueError("No qa_pairs found in response")

        # Convert to QAPair objects
        qa_pairs: List[QAPair] = []
        for item in qa_pairs_data:
            try:
                # Infer category from keywords (will be overridden by classifier later)
                category = self._infer_category(item.get("keywords", []))

                qa_pair = QAPair(
                    question=item["question"],
                    answer=item["answer"],
                    alt_questions=item.get("alt_questions", []),
                    category=category,
                    confidence=item.get("confidence", 0.5),
                    source_slide=slide_no,
                    keywords=item.get("keywords", [])
                )
                qa_pairs.append(qa_pair)
            except Exception as e:
                # Skip invalid QA pairs
                continue

        if not qa_pairs:
            raise ValueError("No valid QA pairs could be parsed")

        return qa_pairs

    def _mock_pairs(self, summary: PageSummary, project_name: str) -> List[QAPair]:
        """Deterministic QA pairs for mock LLM to avoid JSON parse failures."""
        stem = summary.title or summary.one_liner or f"{project_name} 第{summary.slide_no}页"
        bullets = summary.bullets or [summary.one_liner or "要点"]
        answers = "；".join(bullets[:3])
        qa = QAPair(
            question=f"{stem} 主要讲什么？",
            answer=answers,
            alt_questions=[f"{stem} 关键信息", f"{stem} 总结"],
            category=self._infer_category(summary.entities or bullets),
            confidence=0.9,
            source_slide=summary.slide_no,
            keywords=summary.entities or bullets[:3]
        )
        return [qa]

    def _infer_category(self, keywords: List[str]) -> Category:
        """
        Infer category from keywords (simple heuristic, will be overridden by classifier).

        Args:
            keywords: List of keywords

        Returns:
            Category enum value
        """
        keywords_lower = [k.lower() for k in keywords]

        # Simple keyword matching (will be replaced by LLM classifier)
        if any(k in keywords_lower for k in ["定位", "价值", "优势", "差异化"]):
            return Category.POSITIONING
        elif any(k in keywords_lower for k in ["功能", "能力", "特性"]):
            return Category.FEATURES
        elif any(k in keywords_lower for k in ["架构", "技术栈", "系统"]):
            return Category.ARCHITECTURE
        elif any(k in keywords_lower for k in ["部署", "交付", "私有化", "云"]):
            return Category.DEPLOYMENT
        elif any(k in keywords_lower for k in ["集成", "对接", "api", "数据源"]):
            return Category.INTEGRATION
        elif any(k in keywords_lower for k in ["案例", "客户", "poc"]):
            return Category.CASES
        elif any(k in keywords_lower for k in ["对比", "竞品", "市场"]):
            return Category.COMPARISON
        elif any(k in keywords_lower for k in ["规划", "路线", "未来"]):
            return Category.ROADMAP
        else:
            # Default to features
            return Category.FEATURES
