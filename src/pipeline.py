from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from src.config import Settings
from src.extractor import extract_text
from src.models import (
    Manifest,
    PageSummary,
    ProjectProfile,
    SlideText,
    StageMetrics,
    VectorDBMetrics,
)
from src.pipeline_runner import PipelineContext, PipelineRunner, Stage, StageResult
from src.rag import clean_summary_for_embedding, prepare_project_embedding, prepare_slide_embedding
from src.renderer import LibreOfficeRenderer, RenderError
from src.summarizer import LLMClient, PageSummarizer, ProfileGenerator
from src.utils import compute_sha256, ensure_dir, load_json, save_json


# ---------- Stage Implementations ----------
class CaptureStage:
    name = "capture"

    def run(self, ctx: PipelineContext) -> StageResult:
        slides_dir = ctx.output_dir / "slides"
        ensure_dir(slides_dir)

        existing = sorted(slides_dir.glob("*.png"))
        if existing and not ctx.force_capture:
            ctx.log(f"[capture] Reuse {len(existing)} cached slides")
            ctx.artifacts["slides_paths"] = existing
            return StageResult(success_count=len(existing), notes="reuse")

        renderer = LibreOfficeRenderer(
            libreoffice_path=ctx.settings.libreoffice_path,
            pdftoppm_path=ctx.settings.pdftoppm_path,
            dpi=ctx.settings.render_dpi,
        )
        slides_paths = renderer.render(ctx.pptx_path, slides_dir)
        ctx.artifacts["slides_paths"] = slides_paths
        ctx.log(f"[capture] Rendered {len(slides_paths)} slides")
        return StageResult(success_count=len(slides_paths))


class ExtractStage:
    name = "extract"

    def run(self, ctx: PipelineContext) -> StageResult:
        texts_path = ctx.output_dir / "slide_texts.jsonl"
        if texts_path.exists() and not ctx.force_capture:
            with texts_path.open("r", encoding="utf-8") as f:
                slides = [SlideText(**json.loads(line)) for line in f if line.strip()]
            ctx.artifacts["slide_texts"] = slides
            ctx.log(f"[extract] Reuse {len(slides)} extracted slides")
            return StageResult(success_count=len(slides), notes="reuse")

        slides = extract_text(ctx.pptx_path)
        with texts_path.open("w", encoding="utf-8") as f:
            for s in slides:
                f.write(json.dumps(s.model_dump(), ensure_ascii=False) + "\n")
        ctx.artifacts["slide_texts"] = slides
        ctx.log(f"[extract] Extracted text for {len(slides)} slides")
        return StageResult(success_count=len(slides))


class InterpretStage:
    name = "interpret"

    def run(self, ctx: PipelineContext) -> StageResult:
        slide_texts: List[SlideText] = ctx.artifacts.get("slide_texts", [])
        if not slide_texts:
            raise ValueError("No slide_texts in context; run extract stage first.")

        summaries_dir = ctx.output_dir / "page_summaries"
        ensure_dir(summaries_dir)

        existing_files = sorted(summaries_dir.glob("*.json"))
        if existing_files and not ctx.force_interpret and len(existing_files) == len(slide_texts):
            summaries: List[PageSummary] = []
            for path in existing_files:
                data = load_json(path)
                if isinstance(data, list):
                    data = data[0]
                summaries.append(PageSummary(**data))
            ctx.artifacts["summaries"] = summaries
            ctx.log(f"[interpret] Reuse {len(summaries)} summaries")
            return StageResult(success_count=len(summaries), notes="reuse")

        slides_paths: List[Path] = ctx.artifacts.get("slides_paths") or sorted((ctx.output_dir / "slides").glob("*.png"))
        image_map = {int(p.stem): p for p in slides_paths}

        client = LLMClient(ctx.settings)
        page_summarizer = PageSummarizer(client)

        summaries: List[PageSummary] = []
        errors: List[Dict] = []

        ctx.log("[interpret] Generating page summaries ...")
        with ThreadPoolExecutor(max_workers=ctx.settings.max_workers) as executor:
            future_map = {
                executor.submit(self._summarize_single, page_summarizer, slide, image_map.get(slide.slide_no)): slide
                for slide in slide_texts
            }
            for future in as_completed(future_map):
                slide = future_map[future]
                try:
                    summary = future.result()
                    summaries.append(summary)
                    save_json(summary.model_dump(), summaries_dir / f"{slide.slide_no:03d}.json")
                except Exception as exc:  # noqa: BLE001
                    errors.append({"stage": self.name, "slide_no": slide.slide_no, "error": str(exc)})

        summaries.sort(key=lambda s: s.slide_no)
        ctx.artifacts["summaries"] = summaries
        ctx.errors.extend(errors)
        return StageResult(success_count=len(summaries), failure_count=len(errors))

    @staticmethod
    def _summarize_single(
        page_summarizer: PageSummarizer, slide: SlideText, image_path: Optional[Path]
    ) -> PageSummary:
        return page_summarizer.summarize(slide, image_path)


class ProfileStage:
    name = "profile"

    def run(self, ctx: PipelineContext) -> StageResult:
        summaries: List[PageSummary] = ctx.artifacts.get("summaries", [])
        if not summaries:
            return StageResult(success_count=0, failure_count=1, notes="no_summaries")

        profile_dir = ctx.output_dir / "doc_summary"
        ensure_dir(profile_dir)
        profile_path = profile_dir / "project_profile.json"

        if profile_path.exists() and not ctx.force_interpret:
            profile = ProjectProfile(**load_json(profile_path))
            ctx.artifacts["profile"] = profile
            ctx.log("[profile] Reuse existing project profile")
            return StageResult(success_count=1, notes="reuse")

        client = LLMClient(ctx.settings)
        profile = ProfileGenerator(client).generate(summaries)
        ctx.artifacts["profile"] = profile
        save_json(profile.model_dump(), profile_path)
        ctx.log("[profile] Generated project profile")
        return StageResult(success_count=1)


class RAGPrepStage:
    name = "ragprep"

    def run(self, ctx: PipelineContext) -> StageResult:
        summaries: List[PageSummary] = ctx.artifacts.get("summaries", [])
        profile: ProjectProfile | None = ctx.artifacts.get("profile")

        if not summaries or not profile:
            return StageResult(success_count=0, failure_count=1, notes="missing_summaries_or_profile")

        rag_path = ctx.output_dir / "embeddings" / "rag_documents.json"
        ensure_dir(rag_path.parent)

        if rag_path.exists() and not ctx.force_interpret:
            rag_docs = load_json(rag_path)
            ctx.artifacts["rag_docs"] = rag_docs
            ctx.log(f"[ragprep] Reuse {len(rag_docs)} rag documents")
            return StageResult(success_count=len(rag_docs), notes="reuse")

        # Import new RAG modules
        from src.rag.qa_generator import QAGenerator
        from src.rag.classifier import LLMClassifier
        from src.rag.chunk_generator import ChunkGenerator

        project_name = profile.project_name or ctx.pptx_path.stem
        client = LLMClient(ctx.settings)
        qa_generator = QAGenerator(client)
        classifier = LLMClassifier(client, batch_size=8)
        chunk_generator = ChunkGenerator()

        all_chunks: List[Dict] = []
        errors: List[Dict] = []

        ctx.log(f"[ragprep] Generating QA pairs for {len(summaries)} slides...")

        # Step 1: Generate QA pairs (parallel)
        slide_qa_pairs: Dict[int, List] = {}
        with ThreadPoolExecutor(max_workers=ctx.settings.max_workers) as executor:
            future_map = {
                executor.submit(qa_generator.generate_qa_pairs, summary, project_name): summary
                for summary in summaries
            }
            for future in as_completed(future_map):
                summary = future_map[future]
                try:
                    qa_pairs = future.result()
                    slide_qa_pairs[summary.slide_no] = qa_pairs
                except Exception as exc:
                    errors.append({"stage": "qa_generation", "slide_no": summary.slide_no, "error": str(exc)})

        # Step 2: Batch classify QA pairs
        all_qa_pairs = [qa for qas in slide_qa_pairs.values() for qa in qas]
        ctx.log(f"[ragprep] Classifying {len(all_qa_pairs)} QA pairs...")

        try:
            categories = classifier.batch_classify(all_qa_pairs, project_name)
            for qa, category in zip(all_qa_pairs, categories):
                qa.category = category
        except Exception as exc:
            errors.append({"stage": "classification", "error": str(exc)})

        # Step 3: Generate chunks
        ctx.log(f"[ragprep] Generating chunks...")
        for summary in summaries:
            qa_pairs = slide_qa_pairs.get(summary.slide_no, [])

            # QA chunks (primary)
            qa_chunks = chunk_generator.generate_qa_chunks(qa_pairs, project_name)
            all_chunks.extend([c.model_dump() for c in qa_chunks])

            # Additional chunk types
            chunk_types = chunk_generator.decide_chunk_types(summary)
            if "topic" in chunk_types:
                topic_chunks = chunk_generator.generate_topic_chunks(summary, project_name)
                all_chunks.extend([c.model_dump() for c in topic_chunks])
            if "step" in chunk_types:
                step_chunks = chunk_generator.generate_step_chunks(summary, project_name)
                all_chunks.extend([c.model_dump() for c in step_chunks])
            if "metrics" in chunk_types:
                metrics_chunks = chunk_generator.generate_metrics_chunks(summary, project_name)
                all_chunks.extend([c.model_dump() for c in metrics_chunks])

        # Step 4: Project overview chunk
        overview_chunk = chunk_generator.generate_overview_chunk(profile, project_name)
        all_chunks.append(overview_chunk.model_dump())

        # Save
        save_json(all_chunks, rag_path)
        ctx.artifacts["rag_docs"] = all_chunks
        ctx.errors.extend(errors)

        ctx.log(f"[ragprep] Prepared {len(all_chunks)} chunks from {len(summaries)} slides")
        return StageResult(success_count=len(all_chunks), failure_count=len(errors))


class VectorSinkStage:
    name = "vectorsink"

    def __init__(self, inserter) -> None:
        self._inserter = inserter

    def run(self, ctx: PipelineContext) -> StageResult:
        if ctx.no_vectordb or not ctx.settings.vectordb_enabled:
            return StageResult(notes="skipped (disabled)")

        rag_docs: List[Dict] = ctx.artifacts.get("rag_docs", [])
        if not rag_docs:
            return StageResult(failure_count=1, notes="no_rag_docs")

        metrics = self._inserter(rag_docs)
        ctx.artifacts["vectordb_metrics"] = metrics
        return StageResult(success_count=metrics.documents_inserted, failure_count=metrics.documents_failed)


# ---------- Public Pipeline ----------
class PPTPipeline:
    def __init__(self, settings: Settings, verbose: bool = False) -> None:
        self.settings = settings
        self.verbose = verbose

    # Full ingest
    def run(
        self,
        pptx_path: Path,
        output_dir: Path,
        force_rerun: bool = False,
        force_capture: bool = False,
        force_interpret: bool = False,
        no_vectordb: bool = False,
    ) -> Dict:
        pptx_path = pptx_path.resolve()
        output_dir = output_dir.resolve()
        manifest_path = output_dir / "manifest.json"

        ensure_dir(output_dir)

        if manifest_path.exists() and not force_rerun:
            return load_json(manifest_path)

        ctx = PipelineContext(
            pptx_path=pptx_path,
            output_dir=output_dir,
            settings=self.settings,
            force_capture=force_capture,
            force_interpret=force_interpret,
            no_vectordb=no_vectordb,
            verbose=self.verbose,
        )

        stages: List[Stage] = [
            CaptureStage(),
            ExtractStage(),
            InterpretStage(),
            ProfileStage(),
            RAGPrepStage(),
            VectorSinkStage(self._insert_to_vectordb),
        ]

        runner = PipelineRunner(stages)

        start = time.time()
        runner.run(ctx)
        duration = round(time.time() - start, 2)

        slides_paths: List[Path] = ctx.artifacts.get("slides_paths", [])
        summaries: List[PageSummary] = ctx.artifacts.get("summaries", [])
        rag_docs: List[Dict] = ctx.artifacts.get("rag_docs", [])
        vectordb_metrics: VectorDBMetrics | None = ctx.artifacts.get("vectordb_metrics")

        manifest = Manifest(
            input_file=str(pptx_path),
            file_hash=compute_sha256(pptx_path),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            page_count=len(slides_paths),
            errors=ctx.errors,
            duration_seconds=duration,
            output_dir=str(output_dir),
            provider=self.settings.llm_provider,
            model=self.settings.llm_model,
            page_summaries=len(summaries),
            rag_documents=len(rag_docs),
            vectordb_metrics=vectordb_metrics,
            stages=ctx.stage_metrics,
            refine_runs=0,
        )
        save_json(manifest.model_dump(), manifest_path)
        return manifest.model_dump()

    # Refine low-confidence or targeted slides
    def refine(
        self,
        pptx_path: Path,
        output_dir: Path,
        threshold: float = 0.6,
        pages: Optional[str] = None,
    ) -> Dict:
        pptx_path = pptx_path.resolve()
        output_dir = output_dir.resolve()
        manifest_path = output_dir / "manifest.json"
        summaries_dir = output_dir / "page_summaries"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found at {manifest_path}. Run full pipeline first.")

        old_manifest = load_json(manifest_path)
        all_summaries: List[PageSummary] = []
        summary_files = sorted(summaries_dir.glob("*.json"))
        for s_file in summary_files:
            data = load_json(s_file)
            if isinstance(data, list):
                data = data[0]
            all_summaries.append(PageSummary(**data))

        # Targets
        targets: List[int] = []
        if pages:
            targets = [int(p.strip()) for p in pages.split(",") if p.strip()]
        else:
            targets = [s.slide_no for s in all_summaries if s.confidence < threshold]

        if not targets:
            return old_manifest

        # Load slide texts (reuse JSONL if present)
        texts_path = output_dir / "slide_texts.jsonl"
        if texts_path.exists():
            with texts_path.open("r", encoding="utf-8") as f:
                slide_texts = [SlideText(**json.loads(line)) for line in f if line.strip()]
        else:
            slide_texts = extract_text(pptx_path)

        target_texts = [t for t in slide_texts if t.slide_no in targets]
        image_map = {int(p.stem): p for p in (output_dir / "slides").glob("*.png")}

        client = LLMClient(self.settings)
        page_summarizer = PageSummarizer(client)

        refine_logs: List[Dict] = []
        errors: List[Dict] = []

        # Stage metrics collection
        stage_metrics: List[StageMetrics] = []

        # Interpret stage (refine)
        interpret_start = time.time()
        for slide in target_texts:
            try:
                new_summary = page_summarizer.summarize(slide, image_map.get(slide.slide_no))
                for i, s in enumerate(all_summaries):
                    if s.slide_no == slide.slide_no:
                        refine_logs.append(
                            {
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "slide_no": slide.slide_no,
                                "old_confidence": all_summaries[i].confidence,
                                "new_confidence": new_summary.confidence,
                                "provider": self.settings.llm_provider,
                                "model": self.settings.llm_model,
                                "threshold": threshold,
                                "reason": "confidence_below_threshold" if not pages else "manual_selection",
                            }
                        )
                        all_summaries[i] = new_summary
                        break
                save_json(new_summary.model_dump(), summaries_dir / f"{slide.slide_no:03d}.json")
            except Exception as exc:  # noqa: BLE001
                errors.append({"stage": "refine_interpret", "slide_no": slide.slide_no, "error": str(exc)})

        stage_metrics.append(
            StageMetrics(
                name="refine_interpret",
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(interpret_start)),
                ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                duration_seconds=round(time.time() - interpret_start, 2),
                success_count=len(target_texts) - len(errors),
                failure_count=len(errors),
                notes=f"targets={targets}",
            )
        )

        # Profile regeneration
        profile_start = time.time()
        profile_dir = output_dir / "doc_summary"
        ensure_dir(profile_dir)
        profile = None
        try:
            all_summaries.sort(key=lambda x: x.slide_no)
            profile = ProfileGenerator(client).generate(all_summaries)
            save_json(profile.model_dump(), profile_dir / "project_profile.json")
        except Exception as exc:  # noqa: BLE001
            errors.append({"stage": "refine_profile", "error": str(exc)})

        stage_metrics.append(
            StageMetrics(
                name="refine_profile",
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(profile_start)),
                ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                duration_seconds=round(time.time() - profile_start, 2),
                success_count=1 if profile else 0,
                failure_count=0 if profile else 1,
                notes=None,
            )
        )

        # RAG prep
        rag_start = time.time()
        rag_docs: List[Dict] = []
        if profile:
            project_name = profile.project_name or pptx_path.stem
            for summary in all_summaries:
                cleaned_summary, issues = clean_summary_for_embedding(summary)
                rag_docs.append(prepare_slide_embedding(project_name, cleaned_summary))
                for issue in issues:
                    errors.append({"stage": "rag_clean", "slide_no": summary.slide_no, "error": issue})
            rag_docs.append(prepare_project_embedding(project_name, profile))
            rag_path = output_dir / "embeddings" / "rag_documents.json"
            ensure_dir(rag_path.parent)
            save_json(rag_docs, rag_path)
        else:
            errors.append({"stage": "refine_ragprep", "error": "profile_missing"})

        stage_metrics.append(
            StageMetrics(
                name="refine_ragprep",
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(rag_start)),
                ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                duration_seconds=round(time.time() - rag_start, 2),
                success_count=len(rag_docs),
                failure_count=0 if rag_docs else 1,
                notes="vectorsink skipped",
            )
        )

        # Skip vector sink in refine to avoid duplicates

        # Update manifest
        manifest = Manifest(
            input_file=str(pptx_path),
            file_hash=old_manifest.get("file_hash", compute_sha256(pptx_path)),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            page_count=old_manifest.get("page_count", len(all_summaries)),
            errors=errors,
            duration_seconds=0.0,
            output_dir=str(output_dir),
            provider=self.settings.llm_provider,
            model=self.settings.llm_model,
            page_summaries=len(all_summaries),
            rag_documents=len(rag_docs),
            vectordb_metrics=None,
            stages=stage_metrics,
            refine_runs=int(old_manifest.get("refine_runs", 0)) + 1,
        )
        save_json(manifest.model_dump(), manifest_path)

        # Append refine log
        if refine_logs:
            log_path = output_dir / "refine_log.jsonl"
            with log_path.open("a", encoding="utf-8") as f:
                for entry in refine_logs:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return manifest.model_dump()

    # Shared helper
    def _insert_to_vectordb(self, rag_docs: List[Dict]) -> VectorDBMetrics:
        from src.embeddings import M3EEmbedding
        from src.vectordb import ChromaStore

        start = time.time()

        embedding_model = M3EEmbedding(
            model_name=self.settings.embedding_model,
            device=self.settings.embedding_device,
            cache_dir=self.settings.embedding_cache_dir,
        )

        store = ChromaStore(
            persist_dir=self.settings.vectordb_persist_dir,
            collection_name=self.settings.vectordb_collection_name,
            embedding_model=embedding_model,
        )

        success, failure, errors = store.insert_documents(
            rag_docs,
            batch_size=self.settings.embedding_batch_size,
        )

        for err in errors:
            if self.verbose:
                print(f"[vectorsink] error: {err}")

        duration = time.time() - start

        return VectorDBMetrics(
            documents_inserted=success,
            documents_failed=failure,
            embedding_time_seconds=round(duration * 0.7, 2),
            insertion_time_seconds=round(duration * 0.3, 2),
            collection_name=self.settings.vectordb_collection_name,
        )
