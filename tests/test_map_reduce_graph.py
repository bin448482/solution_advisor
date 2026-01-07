import json
from pathlib import Path

import pytest

pytest.importorskip("langgraph.graph")

from src.config import Settings
from src.models import PageSummary
from src.rag.map_reduce_graph import MapReduceCategoryGraph
from src.summarizer import LLMClient


def _summary(slide_no: int, title: str, one_liner: str) -> PageSummary:
    return PageSummary(
        slide_no=slide_no,
        title=title,
        one_liner=one_liner,
        bullets=["bullet"],
        details=f"{one_liner} 详细说明",
        confidence=0.9,
    )


def test_map_reduce_mock_generates_category_and_overview(tmp_path: Path) -> None:
    settings = Settings(
        llm_provider="mock",
        auto_ragprep_enabled=True,
        map_batch_size=2,
        reduce_target_categories=5,
    )
    client = LLMClient(settings)
    output_path = tmp_path / "rag_documents.json"
    graph = MapReduceCategoryGraph(
        settings=settings,
        client=client,
        project_name="demo_project",
        output_path=output_path,
    )

    summaries = [
        _summary(1, "产品定位", "定位与价值"),
        _summary(2, "系统架构", "技术架构"),
        _summary(3, "核心功能", "关键能力"),
    ]

    rag_docs, errors = graph.run(summaries)

    assert errors == []
    assert output_path.exists(), "rag_documents.json should be written"
    assert len(rag_docs) == 4, "3 category summaries + 1 overview"

    category_chunks = [d for d in rag_docs if d["metadata"]["chunk_type"] == "category_summary"]
    overview_chunks = [d for d in rag_docs if d["metadata"]["chunk_type"] == "overview"]

    assert len(category_chunks) == 3
    assert len(overview_chunks) == 1

    # category metadata should carry ids and names, and ids should be unique
    category_ids = [d["metadata"]["category_id"] for d in category_chunks]
    assert all(category_ids), "category_id should not be empty"
    assert len(set(category_ids)) == len(category_ids), "category_id should be unique"

    for chunk in category_chunks:
        meta = chunk["metadata"]
        assert meta["source_slide_refs"], "category_summary should track source slides"
        assert meta["summary"], "category_summary should contain summary text"

    assert set(overview_chunks[0]["metadata"]["source_slide_refs"]) == {1, 2, 3}
