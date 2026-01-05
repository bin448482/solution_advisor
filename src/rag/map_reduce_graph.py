from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypedDict

from langgraph.graph import END, StateGraph

from src.config import Settings
from src.models import PageSummary, ProjectProfile
from src.rag.models import ChunkDocument, ChunkMetadata
from src.summarizer import LLMClient
from src.utils import save_json


class GraphState(TypedDict, total=False):
    """State flowing through the LangGraph pipeline."""

    summaries: List[PageSummary]
    batches: List[List[PageSummary]]
    map_results: List[Dict[str, Any]]
    global_categories: List[Dict[str, Any]]
    reduce_results: List[Dict[str, Any]]
    overview: Dict[str, Any]
    rag_documents: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]


@dataclass
class MapReduceCategoryGraph:
    """
    Map-Reduce style RAGPrep builder orchestrated by LangGraph.

    Inputs:
        - summaries: List[PageSummary]
        - profile: ProjectProfile (optional, only used for overview tone hints)
    Outputs:
        - rag_documents.json containing category_summary + overview chunks
    """

    settings: Settings
    client: LLMClient
    project_name: str
    output_path: Path
    profile: Optional[ProjectProfile] = None

    def __post_init__(self) -> None:
        self._graph = self._build_graph()
        # cache summaries by slide for quick lookups
        self._summary_map: Dict[int, PageSummary] = {}

    # ---------- Public API ----------
    def run(self, summaries: List[PageSummary]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Execute the LangGraph pipeline and persist rag_documents.json."""

        self._summary_map = {s.slide_no: s for s in summaries}
        initial_state: GraphState = {
            "summaries": summaries,
            "map_results": [],
            "reduce_results": [],
            "errors": [],
        }

        final_state: GraphState = self._graph.invoke(initial_state)
        rag_docs = final_state.get("rag_documents", [])
        errors = final_state.get("errors", [])
        return rag_docs, errors

    # ---------- Graph construction ----------
    def _build_graph(self):
        builder = StateGraph(GraphState)
        builder.add_node("prepare_batches", self._node_prepare_batches)
        builder.add_node("map_categories", self._node_map_categories)
        builder.add_node("merge_categories", self._node_merge_categories)
        builder.add_node("reduce_categories", self._node_reduce_categories)
        builder.add_node("build_overview", self._node_build_overview)
        builder.add_node("validate_emit", self._node_validate_emit)

        builder.add_edge("prepare_batches", "map_categories")
        builder.add_edge("map_categories", "merge_categories")
        builder.add_edge("merge_categories", "reduce_categories")
        builder.add_edge("reduce_categories", "build_overview")
        builder.add_edge("build_overview", "validate_emit")
        builder.add_edge("validate_emit", END)
        builder.set_entry_point("prepare_batches")
        return builder.compile()

    # ---------- Node handlers ----------
    def _node_prepare_batches(self, state: GraphState) -> GraphState:
        batches = self._split_batches(state.get("summaries", []), self.settings.map_batch_size)
        return {"batches": batches}

    def _node_map_categories(self, state: GraphState) -> GraphState:
        batches = state.get("batches", [])
        results: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = state.get("errors", []).copy()

        if not batches:
            return {"map_results": [], "errors": errors}

        with ThreadPoolExecutor(max_workers=self.settings.langgraph_max_concurrency) as executor:
            future_map = {
                executor.submit(self._map_single_batch, idx, batch): (idx, batch)
                for idx, batch in enumerate(batches, start=1)
            }
            for future in as_completed(future_map):
                batch_idx, batch = future_map[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:  # noqa: BLE001
                    errors.append({"stage": "map_categories", "batch": batch_idx, "error": str(exc)})

        # keep deterministic ordering by batch index
        results_sorted = sorted(results, key=lambda r: r.get("batch_id", ""))
        return {"map_results": results_sorted, "errors": errors}

    def _node_merge_categories(self, state: GraphState) -> GraphState:
        merged, errors = self._merge_categories(state.get("map_results", []), state.get("errors", []))
        return {"global_categories": merged, "errors": errors}

    def _node_reduce_categories(self, state: GraphState) -> GraphState:
        categories = state.get("global_categories", [])
        errors = state.get("errors", []).copy()
        reduce_results: List[Dict[str, Any]] = []

        if not categories:
            errors.append({"stage": "reduce_categories", "error": "no_global_categories"})
            return {"reduce_results": [], "errors": errors}

        with ThreadPoolExecutor(max_workers=self.settings.langgraph_max_concurrency) as executor:
            future_map = {
                executor.submit(self._reduce_single_category, cat): cat for cat in categories
            }
            for future in as_completed(future_map):
                cat = future_map[future]
                try:
                    reduce_results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    errors.append({"stage": "reduce_categories", "category": cat.get("category_name"), "error": str(exc)})

        reduce_results.sort(key=lambda c: c.get("category_name", ""))
        return {"reduce_results": reduce_results, "errors": errors}

    def _node_build_overview(self, state: GraphState) -> GraphState:
        overview = self._build_overview_chunk(state.get("reduce_results", []))
        return {"overview": overview}

    def _node_validate_emit(self, state: GraphState) -> GraphState:
        rag_docs: List[Dict[str, Any]] = []
        errors = state.get("errors", []).copy()

        reduce_results = state.get("reduce_results", [])
        overview = state.get("overview")

        if not reduce_results:
            errors.append({"stage": "validate_emit", "error": "empty_reduce_results"})

        rag_docs.extend(reduce_results)
        if overview:
            rag_docs.append(overview)

        save_json(rag_docs, self.output_path)
        return {"rag_documents": rag_docs, "errors": errors}

    # ---------- Map helpers ----------
    def _split_batches(self, summaries: Sequence[PageSummary], batch_size: int) -> List[List[PageSummary]]:
        if batch_size <= 0:
            batch_size = 10
        return [list(summaries[i : i + batch_size]) for i in range(0, len(summaries), batch_size)]

    def _map_single_batch(self, batch_idx: int, batch: List[PageSummary]) -> Dict[str, Any]:
        batch_id = f"batch_{batch_idx:02d}"
        if self.client.is_mock:
            return self._mock_map(batch_id, batch)

        prompt = self._render_map_prompt(batch_id, batch)
        raw = self.client.generate(prompt, temperature=self.settings.map_temperature)
        parsed = self._parse_json_block(raw)
        if not parsed or "categories" not in parsed:
            # fallback to heuristic map if parsing fails
            return self._fallback_map(batch_id, batch)
        parsed["batch_id"] = parsed.get("batch_id") or batch_id
        return parsed

    def _render_map_prompt(self, batch_id: str, batch: List[PageSummary]) -> str:
        lines = [
            "你是 PPT 内容整理助手，请基于以下页面摘要做 Map 归类。",
            f"项目: {self.project_name}",
            f"批次: {batch_id}",
            "输出要求：",
            f"- 生成 3-6 个类别，最多 {self.settings.map_max_categories_per_batch} 个；",
            "- 每个类别包含字段: category_name, category_hint, slides(数组), summary(100-150字), qa(最多2条，每条含q/a/source_slide_refs)。",
            "- 仅输出 JSON，不要额外解释。",
            "页面摘要：",
        ]
        for s in batch:
            lines.append(
                json.dumps(
                    {
                        "slide_no": s.slide_no,
                        "title": s.title,
                        "one_liner": s.one_liner,
                        "bullets": s.bullets[:8],
                        "entities": s.entities[:8],
                        "details": (s.details or "")[:200],
                    },
                    ensure_ascii=False,
                )
            )

        schema = {
            "batch_id": batch_id,
            "categories": [
                {
                    "category_name": "string",
                    "category_hint": "string",
                    "slides": [1, 2],
                    "summary": "100-150字摘要",
                    "qa": [
                        {"q": "问题", "a": "答案<=120字", "source_slide_refs": [1, 2]}
                    ],
                }
            ],
        }
        lines.append("JSON 模板示例：")
        lines.append(json.dumps(schema, ensure_ascii=False, indent=2))
        return "\n".join(lines)

    def _fallback_map(self, batch_id: str, batch: List[PageSummary]) -> Dict[str, Any]:
        slides = [s.slide_no for s in batch]
        text = "; ".join(filter(None, [s.title or s.one_liner for s in batch]))
        summary = text[:140] if text else "综合摘要"
        return {
            "batch_id": batch_id,
            "categories": [
                {
                    "category_name": "综合摘要",
                    "category_hint": "general",
                    "slides": slides,
                    "summary": summary,
                    "qa": [],
                }
            ],
        }

    def _mock_map(self, batch_id: str, batch: List[PageSummary]) -> Dict[str, Any]:
        categories = []
        for s in batch:
            categories.append(
                {
                    "category_name": s.title or "综合摘要",
                    "category_hint": "mock",
                    "slides": [s.slide_no],
                    "summary": s.one_liner or (s.details or "")[:120] or "示例摘要",
                    "qa": [
                        {
                            "q": f"{s.title or '本页要点'}是什么？",
                            "a": s.one_liner or "示例回答",
                            "source_slide_refs": [s.slide_no],
                        }
                    ],
                }
            )
        return {"batch_id": batch_id, "categories": categories}

    # ---------- Merge helpers ----------
    def _merge_categories(
        self, map_results: List[Dict[str, Any]], errors: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        merged: Dict[str, Dict[str, Any]] = {}

        for res in map_results:
            for cat in res.get("categories", []):
                name = cat.get("category_name") or "未命名"
                norm = self._normalize_name(name)
                entry = merged.setdefault(
                    norm,
                    {
                        "category_name": name,
                        "category_hint": cat.get("category_hint") or "",
                        "slides": set(),
                        "map_summaries": [],
                        "qa": [],
                    },
                )
                entry["slides"].update(cat.get("slides") or [])
                if cat.get("summary"):
                    entry["map_summaries"].append(cat["summary"])
                entry["qa"].extend(cat.get("qa") or [])

        merged_list = []
        for norm, data in merged.items():
            merged_list.append(
                {
                    "category_name": data["category_name"],
                    "category_hint": data.get("category_hint"),
                    "slides": sorted({int(s) for s in data["slides"]}),
                    "map_summaries": data["map_summaries"],
                    "qa": data["qa"],
                }
            )

        target = self.settings.reduce_target_categories
        if target and len(merged_list) > target:
            merged_list.sort(key=lambda c: len(c.get("slides", [])), reverse=True)
            kept = merged_list[: target - 1]
            overflow = merged_list[target - 1 :]
            other_slides = {s for cat in overflow for s in cat.get("slides", [])}
            other_summaries = [s for cat in overflow for s in cat.get("map_summaries", [])]
            other_qa = [qa for cat in overflow for qa in cat.get("qa", [])]
            kept.append(
                {
                    "category_name": "其他信息",
                    "category_hint": "misc",
                    "slides": sorted(other_slides),
                    "map_summaries": other_summaries,
                    "qa": other_qa,
                }
            )
            merged_list = kept

        merged_list.sort(key=lambda c: c.get("category_name", ""))
        return merged_list, errors

    # ---------- Reduce helpers ----------
    def _reduce_single_category(self, category: Dict[str, Any]) -> Dict[str, Any]:
        name = category.get("category_name") or "未命名"
        slides = category.get("slides", [])
        map_summaries = category.get("map_summaries", [])
        qa_examples = category.get("qa", [])[:5]

        # Build context from slide summaries
        slide_context = []
        for slide_no in slides:
            summary = self._summary_map.get(slide_no)
            if summary:
                slide_context.append(
                    f"Slide {slide_no} | {summary.title or ''} | {summary.one_liner}\n"
                    f"Bullets: {', '.join(summary.bullets[:5])}\n"
                    f"Details: {(summary.details or '')[:180]}"
                )

        summary_text: str
        if self.client.is_mock:
            summary_text = map_summaries[0] if map_summaries else "本类别的汇总摘要。"
        else:
            prompt = self._render_reduce_prompt(name, map_summaries, slide_context, qa_examples)
            raw = self.client.generate(prompt, temperature=self.settings.reduce_temperature)
            parsed = self._parse_json_block(raw)
            if parsed and isinstance(parsed, dict) and parsed.get("summary"):
                summary_text = parsed.get("summary", "")
                qa_examples = parsed.get("qa", qa_examples)
            else:
                summary_text = map_summaries[0] if map_summaries else raw[:260]

        chunk_id = f"{self.project_name}_category_{self._slugify(name)}"
        text_lines = [f"类别: {name}", f"摘要: {summary_text}"]
        if qa_examples:
            text_lines.append("问答：")
            for qa in qa_examples:
                text_lines.append(f"- Q: {qa.get('q')}")
                text_lines.append(f"  A: {qa.get('a')}")

        source_files = [f"page_summaries/{int(s):03d}.json" for s in slides]
        metadata = ChunkMetadata(
            project_name=self.project_name,
            chunk_type="category_summary",
            level="category",
            summary=summary_text,  # type: ignore[arg-type]
            qa_examples=qa_examples,  # type: ignore[arg-type]
            source_slide_refs=slides,
            source_files=source_files,
        )

        chunk = ChunkDocument(
            id=chunk_id,
            text="\n".join(text_lines),
            metadata=metadata.model_dump(),
            original_json=json.dumps({"source_files": source_files, "category": name}, ensure_ascii=False),
        )
        return chunk.model_dump()

    def _render_reduce_prompt(
        self,
        category_name: str,
        map_summaries: Sequence[str],
        slide_context: Sequence[str],
        qa_examples: Sequence[Dict[str, Any]],
    ) -> str:
        lines = [
            "基于 Map 阶段摘要与页面上下文，生成该类别的 Reduce 结果。",
            f"类别: {category_name}",
            "要求：",
            "- summary 200-300 字，覆盖能力/场景/价值/限制；",
            "- 生成 3-5 条 QA，答案 ≤ 200 字，必须引用 slide_no；",
            "- 仅输出 JSON，字段: summary, qa(list[{q,a,source_slide_refs}])。",
            "Map 摘要：",
        ]
        lines.extend([f"- {s}" for s in map_summaries[:8]])
        lines.append("页面上下文：")
        lines.extend([f"- {ctx}" for ctx in slide_context[:8]])
        lines.append("已有 QA（可重写或补充）：")
        lines.extend([json.dumps(qa, ensure_ascii=False) for qa in qa_examples[:5]])
        return "\n".join(lines)

    # ---------- Overview helpers ----------
    def _build_overview_chunk(self, reduce_results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        summaries = []
        slide_refs = set()
        for res in reduce_results:
            metadata = res.get("metadata", {})
            summaries.append(metadata.get("summary") or res.get("text", ""))
            slide_refs.update(metadata.get("source_slide_refs", []))

        summary_text: str
        if self.client.is_mock:
            summary_text = " | ".join(summaries)[:190] if summaries else "项目综述。"
        else:
            prompt = self._render_overview_prompt(summaries)
            raw = self.client.generate(prompt, temperature=self.settings.reduce_temperature)
            parsed = self._parse_json_block(raw)
            if parsed and isinstance(parsed, dict) and parsed.get("overview"):
                summary_text = parsed.get("overview", "")
            else:
                summary_text = raw[:200]

        metadata = ChunkMetadata(
            project_name=self.project_name,
            chunk_type="overview",
            level="project",
            summary=summary_text,  # type: ignore[arg-type]
            source_slide_refs=sorted(slide_refs),
            source_files=["category_summaries"],
        )

        chunk = ChunkDocument(
            id=f"{self.project_name}_overview",
            text=f"项目综述: {summary_text}",
            metadata=metadata.model_dump(),
            original_json=json.dumps({"source": "reduce_results"}, ensure_ascii=False),
        )
        return chunk.model_dump()

    def _render_overview_prompt(self, category_summaries: Sequence[str]) -> str:
        lines = [
            "根据所有类别摘要，生成 150-200 字的项目 overview。",
            "覆盖定位、核心价值、目标用户、亮点/风险，中文输出，严格 JSON：{\"overview\": \"...\"}",
            "类别摘要：",
        ]
        lines.extend([f"- {s}" for s in category_summaries[:12]])
        if self.profile and self.profile.positioning:
            lines.append(f"项目定位提示：{self.profile.positioning}")
        return "\n".join(lines)

    # ---------- Utils ----------
    def _parse_json_block(self, text: str) -> Optional[Any]:
        if not text:
            return None
        # Strip code fences
        fence_match = re.search(r"```(?:json)?(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1)
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            # try to locate first JSON object/array
            obj_match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
            if obj_match:
                snippet = obj_match.group(1)
                try:
                    return json.loads(snippet)
                except Exception:
                    return None
        return None

    def _slugify(self, text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
        slug = re.sub(r"_+", "_", slug).strip("_")
        return slug or "category"

    def _normalize_name(self, name: str) -> str:
        return re.sub(r"\s+", "", name).lower()
