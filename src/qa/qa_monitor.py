"""Monitoring and cache middleware for QA engine.

Implements:
- JSONL logging of each QA call (question, retrieval, LLM metrics, cache status).
- Level 1 exact cache based on normalized question + project.
- Optional level 2 semantic cache stored in a Chroma collection.
"""

from __future__ import annotations

import hashlib
import json
import random
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config import Settings
from src.embeddings import M3EEmbedding


ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QAMonitor:
    """QA monitoring and caching helper."""

    def __init__(
        self,
        settings: Settings,
        *,
        embedding_model: Optional[M3EEmbedding] = None,
        log_dir: Optional[Path] = None,
    ) -> None:
        self.settings = settings
        self.qa_cfg = settings.qa
        self.monitor_cfg = self.qa_cfg.monitor
        self.cache_cfg = self.qa_cfg.cache
        self.embedding_model = embedding_model

        self.log_dir = Path(log_dir or self.monitor_cfg.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.cache_index: Dict[str, Dict[str, Any]] = {}
        self.cache_path = self.log_dir / "qa_cache.jsonl"

        if self.cache_cfg.cache_backend not in {"jsonl", "sqlite"}:
            raise ValueError(f"Unsupported cache backend: {self.cache_cfg.cache_backend}")

        # Load existing cache index (exact cache)
        self._load_cache_index()

        # Semantic cache (Chroma) is optional
        self.semantic_collection = None
        if self.cache_cfg.cache_semantic_enabled and embedding_model is not None:
            self.semantic_collection = self._init_semantic_collection()

    # ---------- public helpers ----------
    @staticmethod
    def normalize_question(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text or "")
        normalized = normalized.strip().lower()
        normalized = " ".join(normalized.split())
        return normalized

    def build_question_id(self, question_norm: str, project_name: Optional[str]) -> str:
        base = f"{question_norm}||{project_name or ''}||{self.cache_cfg.vectordb_version}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    # ---------- cache ----------
    def get_cache(
        self,
        question_id: str,
        *,
        question_norm: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Check exact cache first, then semantic cache."""
        record = self.cache_index.get(question_id)
        if record and not self._is_expired(record):
            return {**record, "cache_level": "exact", "cache_status": "hit"}

        if self.cache_cfg.cache_semantic_enabled and self.semantic_collection:
            return self._semantic_lookup(question_id, question_norm, project_name)

        return None

    def save_cache(self, record: Dict[str, Any]) -> None:
        """Persist successful answer into cache backends."""
        if not self.cache_cfg.cache_enabled:
            return
        if random.random() > self.cache_cfg.cache_sample_rate:
            return

        record = {**record}
        record["cache_level"] = record.get("cache_level", "exact")
        record["cache_status"] = "miss"
        record["created_at"] = record.get("created_at") or _utcnow().strftime(ISO_FMT)
        record["vectordb_version"] = self.cache_cfg.vectordb_version

        # Exact cache JSONL + in-memory index
        self._append_jsonl(self.cache_path, record)
        self.cache_index[record["question_id"]] = record

        # Semantic cache into Chroma
        if self.cache_cfg.cache_semantic_enabled and self.semantic_collection:
            try:
                self._semantic_upsert(record)
            except Exception:
                # Do not raise to caller; logging is best-effort here.
                pass

    # ---------- monitoring ----------
    def log_event(self, event: Dict[str, Any]) -> None:
        if not self.monitor_cfg.monitor_enabled:
            return
        if random.random() > self.monitor_cfg.monitor_sample_rate:
            return

        event = {**event}
        event.setdefault("created_at", _utcnow().strftime(ISO_FMT))
        event.setdefault("trace_id", str(uuid.uuid4()))
        log_path = self.log_dir / f"qa_logs_{_utcnow().strftime('%Y%m%d')}.jsonl"
        self._append_jsonl(log_path, event)

    def make_trace_id(self) -> str:
        return str(uuid.uuid4())

    # ---------- internal helpers ----------
    def _is_expired(self, record: Dict[str, Any]) -> bool:
        try:
            created = datetime.strptime(record["created_at"], ISO_FMT)
        except Exception:
            return True
        delta = _utcnow() - created.replace(tzinfo=timezone.utc)
        if delta > timedelta(days=self.cache_cfg.cache_ttl_days):
            return True
        if str(record.get("vectordb_version")) != str(self.cache_cfg.vectordb_version):
            return True
        return False

    def _append_jsonl(self, path: Path, obj: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False))
            f.write("\n")

    def _load_cache_index(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            for line in self.cache_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if "question_id" in data:
                    self.cache_index[data["question_id"]] = data
        except Exception:
            # Corrupted cache should not block runtime
            self.cache_index = {}

    # ---------- semantic cache helpers ----------
    def _init_semantic_collection(self):
        client = chromadb.PersistentClient(
            path=str(Path(self.cache_cfg.cache_persist_dir)),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        return client.get_or_create_collection(
            name=self.cache_cfg.cache_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def _semantic_upsert(self, record: Dict[str, Any]) -> None:
        if not self.embedding_model:
            return
        question_norm = record.get("question_norm") or ""
        embedding = self.embedding_model.embed_single(question_norm)
        cache_id = f"{record['question_id']}-semantic"
        self.semantic_collection.upsert(
            ids=[cache_id],
            embeddings=[embedding.tolist()],
            documents=[record.get("answer", "")],
            metadatas=[
                {
                    "question_id": record["question_id"],
                    "question_norm": question_norm,
                    "project_name": record.get("project_name"),
                    "created_at": record.get("created_at"),
                    "vectordb_version": self.cache_cfg.vectordb_version,
                }
            ],
        )

    def _semantic_lookup(
        self,
        question_id: str,
        question_norm: Optional[str],
        project_name: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if not self.embedding_model:
            return None

        if not question_norm:
            # semantic lookup requires normalized question; without it we skip
            return None

        embedding = self.embedding_model.embed_single(question_norm)
        where = {"vectordb_version": str(self.cache_cfg.vectordb_version)}
        if project_name:
            where = {"$and": [where, {"project_name": project_name}]}

        results = self.semantic_collection.query(
            query_embeddings=[embedding.tolist()],
            n_results=1,
            where=where,
        )
        if not results or not results.get("ids") or not results["ids"][0]:
            return None

        distance = results["distances"][0][0]
        similarity = 1 - distance if distance is not None else 0
        if similarity < self.cache_cfg.cache_semantic_threshold:
            return None

        meta = results["metadatas"][0][0] or {}
        created_at = meta.get("created_at")
        record = {
            "question_id": meta.get("question_id"),
            "question_norm": meta.get("question_norm"),
            "project_name": meta.get("project_name"),
            "answer": results["documents"][0][0],
            "sources": [],
            "created_at": created_at,
            "cache_level": "semantic",
            "cache_status": "hit",
            "semantic_score": similarity,
            "vectordb_version": meta.get("vectordb_version"),
        }
        if self._is_expired(record):
            return None
        return record
