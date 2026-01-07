from __future__ import annotations

import json
import re
import difflib
from collections import Counter
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
        # track slug usage to ensure category ids remain unique
        self._slug_counts: Counter[str] = Counter()
        # standard category schema（与人工稿对齐）
        self._standard_categories: Dict[str, Dict[str, str]] = {
            "positioning": {"name": "产品定位"},
            "features": {"name": "功能特性"},
            "architecture": {"name": "技术架构"},
            "integration": {"name": "集成对接"},
            "cases": {"name": "客户案例"},
            "comparison": {"name": "竞品对比"},
            "deployment": {"name": "部署运维"},
            "roadmap": {"name": "产品规划"},
        }
        # 允许的别名映射到标准 id
        self._category_alias: Dict[str, str] = {
            "产品定位": "positioning",
            "定位": "positioning",
            "核心定位": "positioning",
            "定位与价值": "positioning",
            "功能特性": "features",
            "核心功能": "features",
            "产品功能": "features",
            "能力": "features",
            "技术架构": "architecture",
            "系统架构": "architecture",
            "架构": "architecture",
            "集成对接": "integration",
            "数据集成": "integration",
            "接入": "integration",
            "客户案例": "cases",
            "案例": "cases",
            "usecase": "cases",
            "竞品对比": "comparison",
            "对比": "comparison",
            "市场对比": "comparison",
            "部署运维": "deployment",
            "落地评估": "deployment",
            "实施运维": "deployment",
            "产品规划": "roadmap",
            "路线图": "roadmap",
            "版本规划": "roadmap",
        }

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

        for chunk in reduce_results:
            ok, msg = self._validate_chunk(chunk)
            if ok:
                rag_docs.append(chunk)
            else:
                errors.append({"stage": "validate_emit", "category": chunk.get("metadata", {}).get("category_name"), "error": msg})

        if overview:
            ok, msg = self._validate_overview(overview)
            if ok:
                rag_docs.append(overview)
            else:
                errors.append({"stage": "validate_emit", "category": "overview", "error": msg})

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
            "- 只能从下列 8 个标准类别中选择（若无匹配则跳过，不要自造类别）：",
            "  positioning(产品定位) / features(功能特性) / architecture(技术架构) / integration(集成对接) / cases(客户案例) / comparison(竞品对比) / deployment(部署运维) / roadmap(产品规划)",
            "- 每个类别包含字段: category_name(用中文标准名), category_hint, slides(数组)。不要生成摘要或问答，这些在 Reduce 阶段完成。",
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
                    "slides": [1, 2]
                }
            ],
        }
        lines.append("JSON 模板示例：")
        lines.append(json.dumps(schema, ensure_ascii=False, indent=2))
        return "\n".join(lines)

    def _fallback_map(self, batch_id: str, batch: List[PageSummary]) -> Dict[str, Any]:
        slides = [s.slide_no for s in batch]
        return {
            "batch_id": batch_id,
            "categories": [
                {
                    "category_name": "综合摘要",
                    "category_hint": "general",
                    "slides": slides,
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
                std_id, std_name, alias_conf = self._map_to_standard_category(name)
                if not std_id:
                    # 非标准类别直接丢弃，避免引入额外 category
                    continue
                norm = std_id
                entry = merged.setdefault(
                    norm,
                    {
                        "category_name": std_name,
                        "category_id": std_id,
                        "category_hint": cat.get("category_hint") or "",
                        "slides": set(),
                        "map_summaries": [],
                        "qa": [],
                        "alias_confidence": alias_conf,
                    },
                )
                entry["slides"].update(cat.get("slides") or [])
                if cat.get("summary"):
                    entry["map_summaries"].append(cat["summary"])

        merged_list = []
        for norm, data in merged.items():
            merged_list.append(
                {
                    "category_name": data["category_name"],
                    "category_id": data.get("category_id"),
                    "category_hint": data.get("category_hint"),
                    "slides": sorted({int(s) for s in data["slides"]}),
                    "map_summaries": data["map_summaries"],
                    "qa": data.get("qa", []),
                    "alias_confidence": data.get("alias_confidence", 0.0),
                }
            )

        merged_list.sort(key=lambda c: c.get("category_name", ""))
        return merged_list, errors

    # ---------- Reduce helpers ----------
    def _reduce_single_category(self, category: Dict[str, Any]) -> Dict[str, Any]:
        name = category.get("category_name") or "未命名"
        slides = category.get("slides", [])
        map_summaries = category.get("map_summaries", [])
        qa_examples = []

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

        # ensure category id uses标准口径
        std_id, std_name, _ = self._map_to_standard_category(name)
        name = std_name
        base_slug = std_id or self._slugify(name)
        idx = self._slug_counts[base_slug]
        self._slug_counts[base_slug] += 1
        slug = base_slug if idx == 0 else f"{base_slug}_{idx + 1}"

        chunk_id = f"{self.project_name}_category_{slug}"
        text_lines = [
            f"项目: {self.project_name}",
            f"【Category】{name}",
            "【Summary】",
            summary_text,
        ]
        if qa_examples:
            text_lines.append("【Representative Q&A】")
            for idx_qa, qa in enumerate(qa_examples, start=1):
                q = qa.get("q") or ""
                a = qa.get("a") or ""
                refs = qa.get("source_slide_refs") or []
                text_lines.append(f"Q{idx_qa}: {q}")
                text_lines.append(f"A{idx_qa}: {a}（来源页: " + ",".join(map(str, refs)) + "）")

        source_files = [f"page_summaries/{int(s):03d}.json" for s in slides]
        metadata = ChunkMetadata(
            project_name=self.project_name,
            chunk_type="category_summary",
            level="category",
            summary=summary_text,  # type: ignore[arg-type]
            qa_examples=qa_examples,  # type: ignore[arg-type]
            category_id=slug,
            category_name=name,
            source_slide_refs=slides,
            source_files=source_files,
        )

        chunk = ChunkDocument(
            id=chunk_id,
            text="\n".join(text_lines),
            metadata=metadata.model_dump(),
            original_json=json.dumps({"source_files": source_files, "category": name, "qa_count": len(qa_examples)}, ensure_ascii=False),
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
        if not summary_text:
            summary_text = " | ".join(summaries)[:200] if summaries else "项目综述。"

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

    def _map_to_standard_category(self, name: str) -> Tuple[str, str, float]:
        """Map arbitrary category name to standard id/name; return confidence.

        - 命中别名：返回标准 id/name，conf=1
        - 模糊匹配 >=0.6：返回最相近标准类
        - 其他：返回 (None, None, 0) 代表不采纳该类别
        """
        norm = self._normalize_name(name)
        if norm in self._category_alias:
            cid = self._category_alias[norm]
            std_name = self._standard_categories[cid]["name"]
            return cid, std_name, 1.0

        candidates = list(self._standard_categories.keys())
        name_pool = candidates + [self._normalize_name(v["name"]) for v in self._standard_categories.values()]
        best_cid = None
        best_conf = -1.0
        for cid in candidates:
            conf = difflib.SequenceMatcher(None, norm, cid).ratio()
            name_conf = difflib.SequenceMatcher(None, norm, self._normalize_name(self._standard_categories[cid]["name"])).ratio()
            conf = max(conf, name_conf)
            if conf > best_conf:
                best_conf = conf
                best_cid = cid

        if best_cid is None:
            return None, None, 0.0

        return best_cid, self._standard_categories[best_cid]["name"], best_conf

    def _slugify(self, text: str) -> str:
        # 保留中英文与数字，将其它符号压缩为下划线；保持语义以便 category_id 可读
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip().lower())
        slug = re.sub(r"_+", "_", slug).strip("_")
        if not slug:
            # 极端情况下退回稳定哈希，确保非空
            import hashlib

            slug = f"category_{hashlib.md5(text.encode('utf-8')).hexdigest()[:8]}"
        return slug

    def _normalize_name(self, name: str) -> str:
        return re.sub(r"\s+", "", name).lower()

    def _validate_chunk(self, chunk: Dict[str, Any]) -> Tuple[bool, str]:
        meta = chunk.get("metadata", {})
        summary = meta.get("summary", "") or ""
        qa = meta.get("qa_examples") or []
        slides = meta.get("source_slide_refs") or []
        if not slides:
            return False, "empty_source_slide_refs"
        # 轻量校验：仅做截断，不因长度/数量失败
        if len(summary) > 360:
            meta["summary"] = summary[:360]
        if len(qa) > 5:
            meta["qa_examples"] = qa[:5]
            qa = meta["qa_examples"]
        missing_refs = False
        for idx, item in enumerate(qa):
            ans = item.get("answer", "") or item.get("a", "") or ""
            refs = item.get("source_slide_refs") or []
            if len(ans) > 220:
                item["answer"] = ans[:220]
            if not refs:
                missing_refs = True
        if missing_refs:
            meta["qa_missing_refs"] = True
        return True, ""

    def _validate_overview(self, chunk: Dict[str, Any]) -> Tuple[bool, str]:
        meta = chunk.get("metadata", {})
        summary = meta.get("summary", "") or ""
        if len(summary) > 260:
            meta["summary"] = summary[:260]
        return True, ""
