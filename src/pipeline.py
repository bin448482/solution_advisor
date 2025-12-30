import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from src.config import Settings
from src.extractor import extract_text
from src.models import Manifest, PageSummary, SlideText
from src.rag import prepare_project_embedding, prepare_slide_embedding
from src.renderer import LibreOfficeRenderer, RenderError
from src.summarizer import LLMClient, PageSummarizer, ProfileGenerator
from src.utils import compute_sha256, ensure_dir, load_json, save_json


class PPTPipeline:
    def __init__(self, settings: Settings, verbose: bool = False) -> None:
        self.settings = settings
        self.verbose = verbose

    def run(self, pptx_path: Path, output_dir: Path, force_rerun: bool = False) -> Dict:
        pptx_path = pptx_path.resolve()
        output_dir = output_dir.resolve()
        slides_dir = output_dir / "slides"
        summaries_dir = output_dir / "page_summaries"
        profile_dir = output_dir / "doc_summary"
        manifest_path = output_dir / "manifest.json"

        ensure_dir(output_dir)

        if manifest_path.exists() and not force_rerun:
            return load_json(manifest_path)

        start = time.time()
        errors: List[Dict] = []
        self._log(f"Rendering slides from {pptx_path} ...")

        renderer = LibreOfficeRenderer(
            libreoffice_path=self.settings.libreoffice_path,
            pdftoppm_path=self.settings.pdftoppm_path,
            dpi=self.settings.render_dpi,
        )
        slides_paths: List[Path]
        try:
            slides_paths = renderer.render(pptx_path, slides_dir)
        except RenderError as exc:
            raise
        texts = extract_text(pptx_path)

        if len(slides_paths) != len(texts):
            errors.append(
                {
                    "stage": "render/extract",
                    "error": f"Mismatch count: slides={len(slides_paths)}, texts={len(texts)}",
                }
            )

        image_map = {idx + 1: path for idx, path in enumerate(slides_paths)}

        client = LLMClient(self.settings)
        page_summarizer = PageSummarizer(client)

        summaries: List[PageSummary] = []
        ensure_dir(summaries_dir)

        self._log("Generating page summaries ...")
        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as executor:
            future_map = {
                executor.submit(self._summarize_single, page_summarizer, slide, image_map.get(slide.slide_no)): slide
                for slide in texts
            }
            for future in as_completed(future_map):
                slide = future_map[future]
                try:
                    summary = future.result()
                    summaries.append(summary)
                    save_json(summary.model_dump(), summaries_dir / f"{slide.slide_no:03d}.json")
                except Exception as exc:  # noqa: BLE001
                    errors.append({"slide_no": slide.slide_no, "error": str(exc)})

        profile = None
        ensure_dir(profile_dir)
        if summaries:
            self._log("Generating project profile ...")
            try:
                profile = ProfileGenerator(client).generate(summaries)
                save_json(profile.model_dump(), profile_dir / "project_profile.json")
            except Exception as exc:  # noqa: BLE001
                errors.append({"stage": "profile", "error": str(exc)})

        # --- RAG Preparation Step ---
        rag_docs: List[Dict] = []
        rag_dir = output_dir / "embeddings"
        ensure_dir(rag_dir)

        if summaries and profile:
            self._log("Preparing RAG documents ...")
            try:
                project_name = profile.project_name or pptx_path.stem
                # 1. Slide embeddings
                for summary in summaries:
                    rag_docs.append(prepare_slide_embedding(project_name, summary))
                # 2. Project embedding
                rag_docs.append(prepare_project_embedding(project_name, profile))
                
                save_json(rag_docs, rag_dir / "rag_documents.json")
            except Exception as exc: # noqa: BLE001
                errors.append({"stage": "rag_prep", "error": str(exc)})
        # ----------------------------

        duration = time.time() - start
        manifest = Manifest(
            input_file=str(pptx_path),
            file_hash=compute_sha256(pptx_path),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            page_count=len(slides_paths),
            errors=errors,
            duration_seconds=round(duration, 2),
            output_dir=str(output_dir),
            provider=self.settings.llm_provider,
            model=self.settings.llm_model,
            page_summaries=len(summaries),
            rag_documents=len(rag_docs),
        )
        save_json(manifest.model_dump(), manifest_path)
        return manifest.model_dump()

    def _summarize_single(
        self, page_summarizer: PageSummarizer, slide: SlideText, image_path: Optional[Path]
    ) -> PageSummary:
        return page_summarizer.summarize(slide, image_path)

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)
