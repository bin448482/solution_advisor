"""Chroma vector database integration for RAG document storage and retrieval."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.embeddings import M3EEmbedding


class ChromaStore:
    """Chroma vector database wrapper for RAG documents.

    Provides document insertion, querying, and management with metadata filtering support.
    """

    def __init__(
        self,
        persist_dir: str,
        collection_name: str,
        embedding_model: M3EEmbedding,
    ):
        """Initialize Chroma client with persistence.

        Args:
            persist_dir: Directory for persistent storage
            collection_name: Name of the collection
            embedding_model: M3E embedding model instance
        """
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.embedding_model = embedding_model

        # Initialize Chroma client with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        self.collection = self.create_or_get_collection()

    def create_or_get_collection(self) -> chromadb.Collection:
        """Create collection if not exists, or get existing.

        Returns:
            Chroma collection instance
        """
        try:
            collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "hnsw:space": "cosine",  # Cosine similarity
                    "hnsw:construction_ef": 200,  # Index build quality
                    "hnsw:search_ef": 100,  # Search quality
                },
            )
            print(f"Collection '{self.collection_name}' ready (count: {collection.count()})")
            return collection
        except Exception as e:
            raise RuntimeError(f"Failed to create/get collection: {e}")

    def insert_documents(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> Tuple[int, int, List[Dict]]:
        """Insert RAG documents into Chroma.

        Args:
            documents: List of RAG documents (from rag_documents.json)
            batch_size: Batch size for insertion

        Returns:
            Tuple of (success_count, failure_count, errors)
        """
        success_count = 0
        failure_count = 0
        errors = []

        # Extract texts for embedding
        texts = [doc["text"] for doc in documents]

        # Generate embeddings in batches
        print(f"Generating embeddings for {len(texts)} documents...")
        try:
            embeddings = self.embedding_model.embed_texts(
                texts,
                batch_size=self.embedding_model.dimension // 8,  # Conservative batch size
                show_progress=True,
            )
        except Exception as e:
            return (0, len(documents), [{"error": f"Embedding generation failed: {e}"}])

        # Insert documents in batches
        print(f"Inserting {len(documents)} documents into Chroma...")
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i : i + batch_size]
            batch_embeddings = embeddings[i : i + batch_size]

            try:
                self._insert_batch(batch_docs, batch_embeddings)
                success_count += len(batch_docs)
            except Exception as e:
                failure_count += len(batch_docs)
                errors.append({
                    "batch_start": i,
                    "batch_size": len(batch_docs),
                    "error": str(e),
                })

        print(f"Insertion complete: {success_count} succeeded, {failure_count} failed")
        return (success_count, failure_count, errors)

    def _insert_batch(
        self,
        documents: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ):
        """Insert a batch of documents with embeddings.

        Args:
            documents: List of RAG documents
            embeddings: List of embedding vectors
        """
        ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadatas = []

        for doc in documents:
            metadata = doc["metadata"].copy()
            # Convert list/dict metadata to JSON strings (Chroma不支持 list/dict)
            for key, val in list(metadata.items()):
                if isinstance(val, list):
                    metadata[key] = json.dumps(val, ensure_ascii=False)
                elif isinstance(val, dict):
                    metadata[key] = json.dumps(val, ensure_ascii=False)
            # Add indexed timestamp
            metadata["indexed_at"] = datetime.utcnow().isoformat() + "Z"
            # Store original JSON
            original_json = doc.get("original_json", "")
            if not isinstance(original_json, (str, int, float, bool)) and original_json is not None:
                original_json = json.dumps(original_json, ensure_ascii=False)
            metadata["original_json"] = original_json
            metadatas.append(metadata)

        # Upsert (insert or update if ID exists - idempotent)
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas,
        )

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict] = None,
    ) -> List[Dict]:
        """Query collection with optional metadata filtering.

        Args:
            query_text: Query text
            n_results: Number of results to return
            where: Metadata filter (e.g., {"project_name": "ChatBI"})

        Returns:
            List of result dictionaries with id, document, metadata, distance
        """
        # Generate query embedding
        query_embedding = self.embedding_model.embed_single(query_text)

        # Query Chroma
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            where=where,
        )

        # Format results
        formatted_results = []
        for i in range(len(results["ids"][0])):
            formatted_results.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })

        return formatted_results

    # ---- Guardrailed query with lightweight rerank ----
    def query_with_guardrails(
        self,
        query_text: str,
        *,
        project_name: Optional[str] = None,
        where: Optional[Dict[str, Any]] = None,
        top_k: int = 8,
        top_n: int = 5,
        tau: float = 0.5,
        detail_keywords: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Query with default project filter, detail-page rerank, and similarity threshold.

        Returns:
            List of result dicts enriched with similarity/score; empty list when below threshold.
        """
        if detail_keywords is None:
            detail_keywords = ["data source", "数据源", "deployment", "部署", "api", "接口", "performance", "性能", "tech stack", "技术栈"]

        where_clause = self._build_where(project_name, where)
        raw_results = self.query(query_text, n_results=top_k, where=where_clause)

        if not raw_results:
            return []

        scored = []
        for r in raw_results:
            similarity = 1 - r["distance"] if r.get("distance") is not None else 0
            meta = r.get("metadata", {}) or {}
            page_types = self._parse_page_types(meta.get("page_type"))
            canonical_types = self._normalize_page_types(page_types)
            score = similarity

            # Slide-level优先
            if str(meta.get("level", "")).lower() == "slide":
                score += 0.02

            # 细节页加分
            if self._has_detail_signal(canonical_types, r.get("document", ""), detail_keywords):
                score += 0.03

            scored.append({
                **r,
                "similarity": similarity,
                "score": score,
                "metadata": {
                    **meta,
                    "page_type": canonical_types,
                },
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        if scored[0]["similarity"] < tau:
            return []

        return scored[:top_n]

    def query_with_qa_ranking(
        self,
        query_text: str,
        *,
        project_name: Optional[str] = None,
        where: Optional[Dict[str, Any]] = None,
        n_results: int = 5,
        category_filter: Optional[List[str]] = None,
        prefer_qa_chunks: bool = True,
        tau: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Enhanced query with QA-aware ranking.

        Args:
            query_text: User question
            project_name: Filter by project
            where: Additional metadata filters
            n_results: Number of results to return
            category_filter: Filter by categories (e.g., ["integration", "features"])
            prefer_qa_chunks: Boost QA chunks in ranking
            tau: Similarity threshold (default: 0.5)

        Returns:
            List of ranked results with metadata
        """
        # Build where clause
        where_clause = self._build_where(project_name, where)

        # Retrieve top_k candidates (2x n_results for reranking)
        top_k = n_results * 2
        raw_results = self.query(query_text, n_results=top_k, where=where_clause)

        if not raw_results:
            return []

        # Rerank with QA-aware scoring
        scored_results = []
        for result in raw_results:
            similarity = 1 - result["distance"] if result.get("distance") is not None else 0
            meta = result.get("metadata", {}) or {}
            score = similarity

            # Boost QA chunks
            if prefer_qa_chunks and meta.get("chunk_type") == "qa_pair":
                score *= 1.2

            # Boost matching categories
            if category_filter:
                result_category = meta.get("category_id")
                if result_category in category_filter:
                    score *= 1.3

            # Boost high confidence
            confidence = meta.get("confidence", 0.5)
            score *= (0.8 + 0.4 * confidence)  # 0.8-1.2x multiplier

            scored_results.append({
                **result,
                "similarity": similarity,
                "score": score,
            })

        # Sort by score and return top N
        scored_results.sort(key=lambda x: x["score"], reverse=True)

        # Apply threshold
        if scored_results and scored_results[0]["similarity"] < tau:
            return []

        return scored_results[:n_results]

    # ---- helpers ----
    def _build_where(self, project_name: Optional[str], where: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if where:
            return where
        if project_name:
            return {"project_name": project_name}
        projects = self.list_projects()
        if len(projects) == 1:
            return {"project_name": projects[0]}
        return None

    @staticmethod
    def _parse_page_types(page_type_field: Any) -> List[str]:
        if page_type_field is None:
            return []
        if isinstance(page_type_field, list):
            return [str(x) for x in page_type_field]
        if isinstance(page_type_field, str):
            try:
                loaded = json.loads(page_type_field)
                if isinstance(loaded, list):
                    return [str(x) for x in loaded]
            except Exception:
                # keep raw string
                return [page_type_field]
        return [str(page_type_field)]

    @staticmethod
    def _normalize_page_types(page_types: List[str]) -> List[str]:
        """Map noisy page_type strings to a small canonical set for rerank signals."""
        if not page_types:
            return []
        mapping = {
            "data": "data_sources",
            "数据": "data_sources",
            "deployment": "deployment",
            "部署": "deployment",
            "api": "api",
            "接口": "api",
            "performance": "performance",
            "性能": "performance",
            "tech": "tech_stack",
            "技术栈": "tech_stack",
            "architecture": "architecture",
            "架构": "architecture",
        }
        canonical: List[str] = []
        for pt in page_types:
            lower = pt.lower()
            hit = None
            for key, val in mapping.items():
                if key in lower:
                    hit = val
                    break
            canonical.append(hit or pt)
        return canonical

    @staticmethod
    def _has_detail_signal(page_types: List[str], text: str, keywords: List[str]) -> bool:
        for pt in page_types:
            if pt in {"data_sources", "deployment", "api", "performance", "tech_stack"}:
                return True
        lower_text = text.lower()
        return any(kw.lower() in lower_text for kw in keywords)

    # ---- Guardrail & Rerank helpers (lightweight; no external deps) ----
    DETAIL_KEYWORDS = [
        "数据源",
        "data source",
        "deployment",
        "部署",
        "api",
        "接口",
        "性能",
        "performance",
        "tech stack",
        "技术栈",
    ]

    def _detail_bonus(self, metadata: Dict[str, Any], document: str) -> float:
        """Heuristic boost for detail slides and critical page types."""
        bonus = 0.0
        if str(metadata.get("level", "")).lower() == "slide":
            bonus += 0.02

        page_types = self._parse_page_types(metadata.get("page_type"))
        for pt in page_types:
            lower = pt.lower()
            if any(keyword.lower() in lower for keyword in self.DETAIL_KEYWORDS):
                bonus += 0.03
                break

        text_lower = document.lower()
        if any(keyword.lower() in text_lower for keyword in self.DETAIL_KEYWORDS):
            bonus += 0.02

        return bonus

    def delete_by_project(self, project_name: str) -> int:
        """Delete all documents for a project.

        Args:
            project_name: Project name to delete

        Returns:
            Number of documents deleted
        """
        # Get all IDs for the project
        results = self.collection.get(
            where={"project_name": project_name},
        )

        if not results["ids"]:
            return 0

        # Delete documents
        self.collection.delete(ids=results["ids"])
        return len(results["ids"])

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics.

        Returns:
            Dictionary with count, projects, etc.
        """
        count = self.collection.count()

        # Get all unique project names
        all_docs = self.collection.get()
        projects = set()
        if all_docs["metadatas"]:
            projects = {meta.get("project_name", "unknown") for meta in all_docs["metadatas"]}

        return {
            "collection_name": self.collection_name,
            "total_documents": count,
            "unique_projects": len(projects),
            "projects": sorted(list(projects)),
        }

    def list_projects(self) -> List[str]:
        """List all unique project names in collection.

        Returns:
            Sorted list of project names
        """
        stats = self.get_collection_stats()
        return stats["projects"]
