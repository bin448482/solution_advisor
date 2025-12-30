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
            # Convert lists to JSON strings (Chroma doesn't support list metadata natively)
            if "page_type" in metadata and isinstance(metadata["page_type"], list):
                metadata["page_type"] = json.dumps(metadata["page_type"])
            if "entities" in metadata and isinstance(metadata["entities"], list):
                metadata["entities"] = json.dumps(metadata["entities"])
            # Add indexed timestamp
            metadata["indexed_at"] = datetime.utcnow().isoformat() + "Z"
            # Store original JSON
            metadata["original_json"] = doc.get("original_json", "")
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
