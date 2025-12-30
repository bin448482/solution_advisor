"""CLI tool for vector database management.

Provides commands for importing, querying, and managing RAG documents in Chroma.
"""

import json
import sys
from pathlib import Path
from typing import List

import click

from src.config import Settings
from src.embeddings import M3EEmbedding
from src.vectordb import ChromaStore


@click.group()
def cli():
    """Vector database management CLI."""
    pass


@cli.command()
@click.option("--input", required=True, help="Path to rag_documents.json")
@click.option("--collection", default="project_slides", help="Collection name")
@click.option("--config", default="config/settings.yaml", help="Config file path")
def import_docs(input: str, collection: str, config: str):
    """Import RAG documents into vector database."""
    try:
        # Load config
        settings = Settings.from_yaml(config)
        settings = settings.with_overrides(vectordb_collection_name=collection)

        # Load documents
        input_path = Path(input)
        if not input_path.exists():
            click.echo(f"Error: Input file not found: {input}", err=True)
            sys.exit(1)

        with open(input_path, "r", encoding="utf-8") as f:
            rag_docs = json.load(f)

        click.echo(f"Loaded {len(rag_docs)} documents from {input}")

        # Initialize embedding model
        click.echo(f"Initializing embedding model: {settings.embedding_model}")
        embedding_model = M3EEmbedding(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            cache_dir=settings.embedding_cache_dir,
        )

        # Initialize vector store
        store = ChromaStore(
            persist_dir=settings.vectordb_persist_dir,
            collection_name=settings.vectordb_collection_name,
            embedding_model=embedding_model,
        )

        # Insert documents
        success, failure, errors = store.insert_documents(
            rag_docs, batch_size=settings.embedding_batch_size
        )

        click.echo(f"\nImport complete:")
        click.echo(f"  ✓ Inserted: {success}")
        click.echo(f"  ✗ Failed: {failure}")

        if errors:
            click.echo(f"\nErrors:")
            for err in errors:
                click.echo(f"  - {err}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--input-dir", required=True, help="Directory with ppt_outputs")
@click.option("--collection", default="project_slides", help="Collection name")
@click.option("--config", default="config/settings.yaml", help="Config file path")
def batch_import(input_dir: str, collection: str, config: str):
    """Batch import all projects from ppt_outputs directory."""
    try:
        # Find all rag_documents.json files
        input_path = Path(input_dir)
        if not input_path.exists():
            click.echo(f"Error: Input directory not found: {input_dir}", err=True)
            sys.exit(1)

        rag_files = list(input_path.glob("*/embeddings/rag_documents.json"))
        if not rag_files:
            click.echo(f"No rag_documents.json files found in {input_dir}")
            sys.exit(0)

        click.echo(f"Found {len(rag_files)} projects to import")

        # Load config
        settings = Settings.from_yaml(config)
        settings = settings.with_overrides(vectordb_collection_name=collection)

        # Initialize embedding model (once for all imports)
        click.echo(f"Initializing embedding model: {settings.embedding_model}")
        embedding_model = M3EEmbedding(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            cache_dir=settings.embedding_cache_dir,
        )

        # Initialize vector store
        store = ChromaStore(
            persist_dir=settings.vectordb_persist_dir,
            collection_name=settings.vectordb_collection_name,
            embedding_model=embedding_model,
        )

        # Import each project
        total_success = 0
        total_failure = 0

        for rag_file in rag_files:
            project_name = rag_file.parent.parent.name
            click.echo(f"\nImporting {project_name}...")

            with open(rag_file, "r", encoding="utf-8") as f:
                rag_docs = json.load(f)

            success, failure, errors = store.insert_documents(
                rag_docs, batch_size=settings.embedding_batch_size
            )

            total_success += success
            total_failure += failure

            click.echo(f"  ✓ {success} documents")
            if failure > 0:
                click.echo(f"  ✗ {failure} failed")

        click.echo(f"\n{'='*50}")
        click.echo(f"Batch import complete:")
        click.echo(f"  Total inserted: {total_success}")
        click.echo(f"  Total failed: {total_failure}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--project", required=True, help="Project name to delete")
@click.option("--collection", default="project_slides", help="Collection name")
@click.option("--config", default="config/settings.yaml", help="Config file path")
@click.confirmation_option(prompt="Are you sure you want to delete this project?")
def delete(project: str, collection: str, config: str):
    """Delete all documents for a project."""
    try:
        # Load config
        settings = Settings.from_yaml(config)
        settings = settings.with_overrides(vectordb_collection_name=collection)

        # Initialize embedding model (needed for ChromaStore init)
        embedding_model = M3EEmbedding(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            cache_dir=settings.embedding_cache_dir,
        )

        # Initialize vector store
        store = ChromaStore(
            persist_dir=settings.vectordb_persist_dir,
            collection_name=settings.vectordb_collection_name,
            embedding_model=embedding_model,
        )

        # Delete project
        deleted_count = store.delete_by_project(project)
        click.echo(f"Deleted {deleted_count} documents for project '{project}'")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--collection", default="project_slides", help="Collection name")
@click.option("--config", default="config/settings.yaml", help="Config file path")
def stats(collection: str, config: str):
    """Show collection statistics."""
    try:
        # Load config
        settings = Settings.from_yaml(config)
        settings = settings.with_overrides(vectordb_collection_name=collection)

        # Initialize embedding model
        embedding_model = M3EEmbedding(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            cache_dir=settings.embedding_cache_dir,
        )

        # Initialize vector store
        store = ChromaStore(
            persist_dir=settings.vectordb_persist_dir,
            collection_name=settings.vectordb_collection_name,
            embedding_model=embedding_model,
        )

        # Get statistics
        stats = store.get_collection_stats()

        click.echo(f"\nCollection: {stats['collection_name']}")
        click.echo(f"Total documents: {stats['total_documents']}")
        click.echo(f"Unique projects: {stats['unique_projects']}")
        click.echo(f"\nProjects:")
        for project in stats["projects"]:
            click.echo(f"  - {project}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--text", required=True, help="Query text")
@click.option("--collection", default="project_slides", help="Collection name")
@click.option("--config", default="config/settings.yaml", help="Config file path")
@click.option("--top-k", default=5, help="Number of results")
@click.option("--project", default=None, help="Filter by project name")
def query(text: str, collection: str, config: str, top_k: int, project: str):
    """Query the vector database."""
    try:
        # Load config
        settings = Settings.from_yaml(config)
        settings = settings.with_overrides(vectordb_collection_name=collection)

        # Initialize embedding model
        click.echo(f"Initializing embedding model...")
        embedding_model = M3EEmbedding(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            cache_dir=settings.embedding_cache_dir,
        )

        # Initialize vector store
        store = ChromaStore(
            persist_dir=settings.vectordb_persist_dir,
            collection_name=settings.vectordb_collection_name,
            embedding_model=embedding_model,
        )

        # Build filter
        where = {"project_name": project} if project else None

        # Query
        click.echo(f"\nQuerying: '{text}'")
        if where:
            click.echo(f"Filter: {where}")

        results = store.query(query_text=text, n_results=top_k, where=where)

        click.echo(f"\nFound {len(results)} results:\n")
        for i, result in enumerate(results, 1):
            click.echo(f"[{i}] ID: {result['id']}")
            click.echo(f"    Distance: {result['distance']:.4f}")
            click.echo(f"    Project: {result['metadata'].get('project_name', 'N/A')}")
            click.echo(f"    Slide: {result['metadata'].get('slide_no', 'N/A')}")
            click.echo(f"    Level: {result['metadata'].get('level', 'N/A')}")
            click.echo(f"    Text: {result['document'][:150]}...")
            click.echo()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--collection", default="project_slides", help="Collection name")
@click.option("--config", default="config/settings.yaml", help="Config file path")
def list_projects(collection: str, config: str):
    """List all projects in the collection."""
    try:
        # Load config
        settings = Settings.from_yaml(config)
        settings = settings.with_overrides(vectordb_collection_name=collection)

        # Initialize embedding model
        embedding_model = M3EEmbedding(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            cache_dir=settings.embedding_cache_dir,
        )

        # Initialize vector store
        store = ChromaStore(
            persist_dir=settings.vectordb_persist_dir,
            collection_name=settings.vectordb_collection_name,
            embedding_model=embedding_model,
        )

        # List projects
        projects = store.list_projects()

        click.echo(f"\nProjects in collection '{collection}':")
        for project in projects:
            click.echo(f"  - {project}")
        click.echo(f"\nTotal: {len(projects)} projects")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
