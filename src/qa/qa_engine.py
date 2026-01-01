"""轻量级问答引擎，基于向量检索结果构建上下文并调用 LLM 生成答案。"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from src.qa.qa_monitor import QAMonitor

from src.summarizer.llm_client import LLMClient
from src.vectordb.chroma_store import ChromaStore


PROMPT_TEMPLATE = """
你是一个专业的解决方案顾问助手。请基于以下检索到的文档内容回答用户问题。

写作要求：
1. 只能使用文档中出现的信息，不要编造或引入外部知识。
2. 如果文档中没有相关信息，请明确说明「文档中未提及」。
3. 结合用户问题，用自然、通俗、连贯的中文表述，尽量把能从文档推断的细节讲清楚，但不要臆测。
4. 在回答里自然点出来源（如“根据第X页…”）。

检索到的文档:
{context}

用户问题: {question}

请回答:
"""


class QAEngine:
    """基于向量检索 + LLM 的单轮问答引擎。"""

    def __init__(self, store: ChromaStore, llm_client: LLMClient, monitor: Optional[QAMonitor] = None):
        self.store = store
        self.llm = llm_client
        self.monitor = monitor

    def answer(
        self,
        question: str,
        project_name: Optional[str] = None,
        top_k: int = 8,
        top_n: int = 5,
        tau: float = 0.5,
    ) -> Dict[str, Any]:
        """执行问答：检索 -> 构建提示 -> 调用 LLM -> 返回结构化结果。"""

        trace_id = self.monitor.make_trace_id() if self.monitor else None
        question_norm = QAMonitor.normalize_question(question) if self.monitor else None
        question_id = (
            self.monitor.build_question_id(question_norm, project_name) if self.monitor else None
        )

        if self.monitor and self.monitor.cache_cfg.cache_enabled:
            cached = self.monitor.get_cache(
                question_id,
                question_norm=question_norm,
                project_name=project_name,
            )
            if cached:
                hit_response = {
                    "answer": cached.get("answer", ""),
                    "sources": cached.get("sources", []),
                    "status": "success",
                    "cache_status": cached.get("cache_status", "hit"),
                    "cache_level": cached.get("cache_level", "exact"),
                    "cached_at": cached.get("created_at"),
                }
                self.monitor.log_event(
                    {
                        "trace_id": trace_id,
                        "question_id": question_id,
                        "question_norm": question_norm,
                        "question_raw": question,
                        "project_name": project_name,
                        "cache_status": cached.get("cache_status", "hit"),
                        "cache_level": cached.get("cache_level", "exact"),
                        "total_latency_ms": 0,
                        "status": "success",
                    }
                )
                return hit_response

        retrieval_start = time.time()
        try:
            results = self.store.query_with_guardrails(
                query_text=question,
                project_name=project_name,
                top_k=top_k,
                top_n=top_n,
                tau=tau,
            )
        except Exception as e:  # pragma: no cover - passthrough to caller
            if self.monitor:
                self.monitor.log_event(
                    {
                        "trace_id": trace_id,
                        "question_id": question_id,
                        "question_norm": question_norm,
                        "question_raw": question,
                        "project_name": project_name,
                        "cache_status": "miss",
                        "status": "error",
                        "error": str(e),
                    }
                )
            return {
                "answer": "检索失败，请稍后重试。",
                "sources": [],
                "status": "error",
                "error": str(e),
            }
        retrieval_ms = int((time.time() - retrieval_start) * 1000)

        normalized = self._normalize_results(results, top_n)
        if not normalized["contexts"]:
            if self.monitor:
                self.monitor.log_event(
                    {
                        "trace_id": trace_id,
                        "question_id": question_id,
                        "question_norm": question_norm,
                        "question_raw": question,
                        "project_name": project_name,
                        "retrieval": {"results": results, "top_k": top_k, "top_n": top_n, "tau": tau},
                        "cache_status": "miss",
                        "status": "no_context",
                        "retrieval_latency_ms": retrieval_ms,
                    }
                )
            return {
                "answer": "未找到相关内容，无法回答该问题。",
                "sources": [],
                "status": "no_context",
            }

        prompt = self._build_prompt(question, normalized["contexts"])

        llm_start = time.time()
        try:
            answer_text = self.llm.generate(prompt)
        except Exception as e:  # pragma: no cover - passthrough to caller
            if self.monitor:
                self.monitor.log_event(
                    {
                        "trace_id": trace_id,
                        "question_id": question_id,
                        "question_norm": question_norm,
                        "question_raw": question,
                        "project_name": project_name,
                        "retrieval": {"results": results, "top_k": top_k, "top_n": top_n, "tau": tau},
                        "cache_status": "miss",
                        "status": "error",
                        "retrieval_latency_ms": retrieval_ms,
                        "llm_latency_ms": int((time.time() - llm_start) * 1000),
                        "error": str(e),
                    }
                )
            return {
                "answer": "生成回答时出现错误，请稍后重试。",
                "sources": normalized["sources"],
                "status": "error",
                "error": str(e),
            }
        llm_latency_ms = int((time.time() - llm_start) * 1000)

        response = {
            "answer": answer_text.strip(),
            "sources": normalized["sources"],
            "status": "success",
            "cache_status": "miss",
        }

        if self.monitor:
            log_event = {
                "trace_id": trace_id,
                "question_id": question_id,
                "question_norm": question_norm,
                "question_raw": question,
                "project_name": project_name,
                "retrieval": {
                    "query_text": question,
                    "top_k": top_k,
                    "top_n": top_n,
                    "tau": tau,
                    "results": results,
                },
                "llm": {
                    "model": self.llm.settings.llm_model if hasattr(self.llm, "settings") else None,
                    "latency_ms": llm_latency_ms,
                    "status": "success",
                },
                "cache_status": "miss",
                "status": "success",
                "retrieval_latency_ms": retrieval_ms,
                "total_latency_ms": retrieval_ms + llm_latency_ms,
            }
            self.monitor.log_event(log_event)

            if self.monitor.cache_cfg.cache_enabled and response["status"] == "success":
                cache_record = {
                    "question_id": question_id,
                    "question_norm": question_norm,
                    "question_raw": question,
                    "project_name": project_name,
                    "answer": response["answer"],
                    "sources": response["sources"],
                    "status": response["status"],
                }
                self.monitor.save_cache(cache_record)

        return response

    @staticmethod
    def _build_prompt(question: str, contexts: List[str]) -> str:
        context_block = "\n\n".join(contexts)
        return PROMPT_TEMPLATE.format(context=context_block, question=question)

    @staticmethod
    def _normalize_results(results: List[Dict[str, Any]], top_n: int) -> Dict[str, Any]:
        """提取上下文与来源信息，并处理 guardrail 的空结果。"""
        if not results:
            return {"contexts": [], "sources": []}

        # Guardrail 返回无结果的情况
        if len(results) == 1 and isinstance(results[0], dict) and results[0].get("message"):
            return {"contexts": [], "sources": []}

        contexts: List[str] = []
        sources: List[Dict[str, Any]] = []

        for idx, item in enumerate(results[:top_n], 1):
            metadata = item.get("metadata", {}) or {}
            project = metadata.get("project_name") or metadata.get("source") or "未知项目"
            slide_no = metadata.get("slide_no", "N/A")
            level = metadata.get("level", "unknown")
            similarity = item.get("similarity")
            if similarity is not None:
                similarity = round(float(similarity), 4)

            doc_text = item.get("document") or item.get("text") or ""
            contexts.append(f"[文档{idx}] 项目: {project}, 页码: {slide_no}\n{doc_text}")

            sources.append(
                {
                    "project": project,
                    "slide_no": slide_no,
                    "similarity": similarity,
                    "level": level,
                }
            )

        return {"contexts": contexts, "sources": sources}

