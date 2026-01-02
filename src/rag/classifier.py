"""
LLM-based Batch Classifier

Classifies QA pairs into 8 categories using batch processing for efficiency.
"""
import json
import time
from typing import List

from src.summarizer.llm_client import LLMClient
from src.rag.models import QAPair, Category


# Batch Classification Prompt Template (Chinese)
BATCH_CLASSIFICATION_PROMPT = """你是一个专业的内容分类专家。请将以下{count}个问答对分类到最合适的类别中。

项目: {project_name}

类别定义:
1. positioning - 产品定位、核心价值、目标用户、差异化优势
2. features - 功能特性、核心能力、产品亮点
3. architecture - 技术架构、系统设计、技术栈、架构图
4. deployment - 部署方式、交付模式、私有化、云原生
5. integration - 集成对接、API、数据源、第三方系统
6. cases - 客户案例、POC、试点、成功案例
7. comparison - 竞品对比、市场分析、优劣势
8. roadmap - 产品规划、未来方向、路线图

问答对列表:
{qa_list}

请为每个问答对选择最合适的类别，输出JSON:
{{
  "classifications": [
    {{
      "qa_index": 1,
      "category": "integration",
      "reasoning": "该问答涉及数据源连接和集成能力"
    }},
    {{
      "qa_index": 2,
      "category": "features",
      "reasoning": "该问答描述产品的核心功能特性"
    }}
  ]
}}

注意:
- 每个问答对必须分配一个类别
- 选择最贴切的类别，如果有多个可能，选择最主要的
- reasoning 简短说明分类理由（可选，用于调试）
"""


class LLMClassifier:
    """Batch classifier for QA pairs using LLM."""

    def __init__(self, llm_client: LLMClient, batch_size: int = 8):
        """
        Initialize classifier.

        Args:
            llm_client: LLM client for API calls
            batch_size: Number of QA pairs to classify in one batch (default: 8)
        """
        self.llm_client = llm_client
        self.batch_size = batch_size

    def batch_classify(
        self,
        qa_pairs: List[QAPair],
        project_name: str,
        max_retries: int = 3
    ) -> List[Category]:
        """
        Classify multiple QA pairs in batches.

        Args:
            qa_pairs: List of QAPair objects to classify
            project_name: Project name for context
            max_retries: Maximum retry attempts per batch

        Returns:
            List of Category values (same order as input)
        """
        if not qa_pairs:
            return []

        all_categories: List[Category] = []

        # Process in batches
        for i in range(0, len(qa_pairs), self.batch_size):
            batch = qa_pairs[i:i + self.batch_size]
            batch_categories = self._classify_batch(batch, project_name, max_retries)
            all_categories.extend(batch_categories)

        return all_categories

    def _classify_batch(
        self,
        batch: List[QAPair],
        project_name: str,
        max_retries: int
    ) -> List[Category]:
        """
        Classify a single batch of QA pairs.

        Args:
            batch: List of QAPair objects (up to batch_size)
            project_name: Project name for context
            max_retries: Maximum retry attempts

        Returns:
            List of Category values for this batch
        """
        # Format QA list for prompt
        qa_list_text = ""
        for idx, qa in enumerate(batch, 1):
            qa_list_text += f"{idx}. 问题: {qa.question}\n"
            qa_list_text += f"   答案: {qa.answer[:100]}{'...' if len(qa.answer) > 100 else ''}\n\n"

        # Build prompt
        prompt = BATCH_CLASSIFICATION_PROMPT.format(
            count=len(batch),
            project_name=project_name,
            qa_list=qa_list_text
        )

        # Retry logic with exponential backoff
        for attempt in range(max_retries):
            try:
                response = self.llm_client.generate(prompt)
                categories = self._parse_classification_response(response, len(batch))

                if len(categories) != len(batch):
                    raise ValueError(
                        f"Expected {len(batch)} classifications, got {len(categories)}"
                    )

                return categories

            except Exception as exc:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    time.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed - use fallback categories
                    return [qa.category for qa in batch]  # Keep existing categories

    def _parse_classification_response(
        self,
        response: str,
        expected_count: int
    ) -> List[Category]:
        """
        Parse LLM classification response.

        Args:
            response: Raw LLM response (JSON string)
            expected_count: Expected number of classifications

        Returns:
            List of Category values

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
                lines = response.split("\n")
                response = "\n".join(lines[1:-1]) if len(lines) > 2 else response
            try:
                data = json.loads(response)
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse classification response as JSON: {e}")

        # Extract classifications array
        classifications = data.get("classifications", [])
        if not classifications:
            raise ValueError("No classifications found in response")

        # Sort by qa_index to ensure correct order
        classifications.sort(key=lambda x: x.get("qa_index", 0))

        # Convert to Category enum
        categories: List[Category] = []
        for item in classifications:
            category_str = item.get("category", "features")
            try:
                category = Category(category_str)
            except ValueError:
                # Invalid category, default to features
                category = Category.FEATURES
            categories.append(category)

        return categories
