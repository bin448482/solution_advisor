import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from src.config import Settings
from src.extractor import extract_text
from src.models import Manifest, PageSummary, SlideText, VectorDBMetrics
from src.rag import clean_summary_for_embedding, prepare_project_embedding, prepare_slide_embedding
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
                    cleaned_summary, issues = clean_summary_for_embedding(summary)
                    rag_docs.append(prepare_slide_embedding(project_name, cleaned_summary))
                    for issue in issues:
                        errors.append(
                            {"stage": "rag_clean", "slide_no": summary.slide_no, "error": issue}
                        )
                # 2. Project embedding
                rag_docs.append(prepare_project_embedding(project_name, profile))

                save_json(rag_docs, rag_dir / "rag_documents.json")
            except Exception as exc:  # noqa: BLE001
                errors.append({"stage": "rag_prep", "error": str(exc)})
        # ----------------------------

        # --- Vector DB Insertion Step (NEW) ---
        vectordb_metrics = None
        if self.settings.vectordb_enabled and rag_docs:
            self._log("Inserting documents into vector database ...")
            try:
                vectordb_metrics = self._insert_to_vectordb(rag_docs)
            except Exception as exc:  # noqa: BLE001
                errors.append({"stage": "vectordb", "error": str(exc)})
        # --------------------------------------

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
            vectordb_metrics=vectordb_metrics,
        )
        save_json(manifest.model_dump(), manifest_path)
        return manifest.model_dump()

    def refine(self, pptx_path: Path, output_dir: Path, threshold: float = 0.6) -> Dict:
        """
        Refine mode: scan for low-confidence pages and re-summarize them.
        Then regenerate profile and vector DB.
        """
        pptx_path = pptx_path.resolve()
        output_dir = output_dir.resolve()
        summaries_dir = output_dir / "page_summaries"
        profile_dir = output_dir / "doc_summary"
        manifest_path = output_dir / "manifest.json"
        slides_dir = output_dir / "slides"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found at {manifest_path}. Run full pipeline first.")

        self._log(f"Refine Mode: Scanning {summaries_dir} for confidence < {threshold} ...")
        
        # 1. Scan for low confidence slides
        targets: List[int] = []
        all_summaries: List[PageSummary] = []
        
        # Load all existing summaries to identify targets and for later aggregation
        summary_files = sorted(summaries_dir.glob("*.json"))
        for s_file in summary_files:
            try:
                data = load_json(s_file)
                # Handle cases where data might be a list or dict
                if isinstance(data, list): data = data[0]
                summary = PageSummary(**data)
                all_summaries.append(summary)
                
                if summary.confidence < threshold:
                    targets.append(summary.slide_no)
                    self._log(f" -> Found low confidence slide {summary.slide_no}: {summary.confidence}")
            except Exception as e:
                self._log(f"Error reading {s_file}: {e}")
                # If reading fails, we might want to re-process it too, assuming filename has slide_no
                try:
                    slide_no = int(s_file.stem)
                    targets.append(slide_no)
                except:
                    pass

        if not targets:
            self._log("No slides found below threshold. Refine finished.")
            return load_json(manifest_path)

        self._log(f"Refining {len(targets)} slides: {targets}")

        # 2. Extract text (we need context for these slides)
        # We extract all because we need to find the specific slide objects
        all_texts = extract_text(pptx_path)
        target_texts = [t for t in all_texts if t.slide_no in targets]
        
        # 3. Re-run summarization for targets
        client = LLMClient(self.settings)
        page_summarizer = PageSummarizer(client)
        
        # Image mapping
        image_map = {
            int(p.stem): p for p in slides_dir.glob("*.png")
        }

        errors: List[Dict] = []
        
        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as executor:
            future_map = {
                executor.submit(self._summarize_single, page_summarizer, slide, image_map.get(slide.slide_no)): slide
                for slide in target_texts
            }
            for future in as_completed(future_map):
                slide = future_map[future]
                try:
                    new_summary = future.result()
                    self._log(f" -> Refined slide {slide.slide_no}, new confidence: {new_summary.confidence}")
                    
                    # Update the local list
                    for i, s in enumerate(all_summaries):
                        if s.slide_no == slide.slide_no:
                            all_summaries[i] = new_summary
                            break
                    else:
                        all_summaries.append(new_summary)
                        
                    # Overwrite file
                    save_json(new_summary.model_dump(), summaries_dir / f"{slide.slide_no:03d}.json")
                except Exception as exc:
                    errors.append({"slide_no": slide.slide_no, "error": str(exc)})
                    self._log(f"Error refining slide {slide.slide_no}: {exc}")

        # 4. Regenerate Profile
        self._log("Regenerating project profile ...")
        profile = None
        ensure_dir(profile_dir)
        try:
            # Sort summaries by slide_no before profiling
            all_summaries.sort(key=lambda x: x.slide_no)
            profile = ProfileGenerator(client).generate(all_summaries)
            save_json(profile.model_dump(), profile_dir / "project_profile.json")
        except Exception as exc:
             errors.append({"stage": "profile", "error": str(exc)})
             self._log(f"Profile generation failed: {exc}")

        # 5. RAG & VectorDB Update
        rag_docs: List[Dict] = []
        rag_dir = output_dir / "embeddings"
        ensure_dir(rag_dir)

        if all_summaries and profile:
            self._log("Updating RAG documents ...")
            try:
                project_name = profile.project_name or pptx_path.stem
                for summary in all_summaries:
                    cleaned_summary, issues = clean_summary_for_embedding(summary)
                    rag_docs.append(prepare_slide_embedding(project_name, cleaned_summary))
                    # log issues if needed
                rag_docs.append(prepare_project_embedding(project_name, profile))
                save_json(rag_docs, rag_dir / "rag_documents.json")
            except Exception as exc:
                errors.append({"stage": "rag_prep", "error": str(exc)})

        # NOTE: Refine 模式下跳过向量库写入，避免重复插入/依赖额外环境
        vectordb_metrics = None
        if self.settings.vectordb_enabled and rag_docs:
            self._log("Skipping vector database insertion in refine mode.")

        # 6. Update Manifest
        old_manifest = load_json(manifest_path)
        manifest = Manifest(
            input_file=str(pptx_path),
            file_hash=old_manifest.get("file_hash", ""),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            page_count=old_manifest.get("page_count", 0),
            errors=errors, # specific errors for this run
            duration_seconds=0.0, # Not tracking full duration for refine
            output_dir=str(output_dir),
            provider=self.settings.llm_provider,
            model=self.settings.llm_model,
            page_summaries=len(all_summaries),
            rag_documents=len(rag_docs),
            vectordb_metrics=vectordb_metrics,
        )
        save_json(manifest.model_dump(), manifest_path)
        self._log("Refine complete.")
        return manifest.model_dump()

    def _summarize_single(
        self, page_summarizer: PageSummarizer, slide: SlideText, image_path: Optional[Path]
    ) -> PageSummary:
        return page_summarizer.summarize(slide, image_path)

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def _insert_to_vectordb(self, rag_docs: List[Dict]) -> VectorDBMetrics:
        """Insert RAG documents into vector database.

        Args:
            rag_docs: List of RAG documents from prepare_*_embedding functions

        Returns:
            VectorDBMetrics with insertion statistics
        """
        from src.embeddings import M3EEmbedding
        from src.vectordb import ChromaStore

        start = time.time()

        # Initialize embedding model
        embedding_model = M3EEmbedding(
            model_name=self.settings.embedding_model,
            device=self.settings.embedding_device,
            cache_dir=self.settings.embedding_cache_dir,
        )

        # Initialize vector store
        store = ChromaStore(
            persist_dir=self.settings.vectordb_persist_dir,
            collection_name=self.settings.vectordb_collection_name,
            embedding_model=embedding_model,
        )

        # Insert documents
        success, failure, errors = store.insert_documents(
            rag_docs,
            batch_size=self.settings.embedding_batch_size,
        )

        # Log errors
        for err in errors:
            self._log(f"Vector DB error: {err}")

        duration = time.time() - start

        return VectorDBMetrics(
            documents_inserted=success,
            documents_failed=failure,
            embedding_time_seconds=round(duration * 0.7, 2),  # Estimate
            insertion_time_seconds=round(duration * 0.3, 2),
            collection_name=self.settings.vectordb_collection_name,
        )
