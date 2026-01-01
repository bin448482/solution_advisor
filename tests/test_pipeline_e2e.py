from pathlib import Path
import shutil

import pytest

from src.config import Settings
from src.pipeline import PPTPipeline


PPT_SAMPLE = Path("ppts/ChatBI产品介绍_2025.pptx")


requires_render = pytest.mark.skipif(
    shutil.which("soffice") is None or shutil.which("pdftoppm") is None,
    reason="LibreOffice or pdftoppm not available",
)


@pytest.mark.skipif(not PPT_SAMPLE.exists(), reason="sample PPT not found")
@requires_render
def test_pipeline_smoke(tmp_path):
    settings = Settings(llm_provider="mock")
    pipeline = PPTPipeline(settings=settings, verbose=False)
    output_dir = tmp_path / "run"
    manifest = pipeline.run(pptx_path=PPT_SAMPLE, output_dir=output_dir, force_rerun=True)

    assert manifest["page_count"] >= 1
    assert (output_dir / "slides").exists()
    assert (output_dir / "page_summaries").exists()
    assert (output_dir / "embeddings" / "rag_documents.json").exists()
    assert manifest["rag_documents"] >= 1
