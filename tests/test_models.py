from src.models import Manifest, PageSummary, ProjectProfile


def test_manifest_defaults():
    manifest = Manifest(
        input_file="demo.pptx",
        file_hash="abc",
        timestamp="2024-01-01T00:00:00Z",
        page_count=1,
        errors=[],
        duration_seconds=1.0,
        output_dir="/tmp/out",
        provider="mock",
        model="mock-model",
        page_summaries=1,
    )
    assert manifest.page_count == 1
    assert manifest.provider == "mock"


def test_profile_model_fields():
    profile = ProjectProfile(core_capabilities=["analysis"], evidence_map={"capability": [1]})
    assert "analysis" in profile.core_capabilities
    assert profile.evidence_map["capability"] == [1]


def test_page_summary_model_defaults():
    summary = PageSummary(slide_no=1, one_liner="x")
    assert summary.confidence == 0.0
    assert summary.bullets == []
