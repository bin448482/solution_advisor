# Scripts Module (src/scripts/)

Standalone command-line tools for vector database management.

## Overview

This module provides CLI tools for managing the vector database independently of the main PPT parsing pipeline. Useful for batch operations, debugging, and manual data management.

## vectordb_cli.py

Command-line interface for Chroma vector database operations.

### Commands

#### import

Import RAG documents from a single rag_documents.json file.

```bash
python -m src.scripts.vectordb_cli import \
    --input ppt_outputs/ChatBI/embeddings/rag_documents.json \
    --collection project_slides \
    --config config/settings.yaml
```

**Options**:
- `--input`: Path to rag_documents.json (required)
- `--collection`: Collection name (default: project_slides)
- `--config`: Config file path (default: config/settings.yaml)

**Output**:
```
Loaded 41 documents from ppt_outputs/ChatBI/embeddings/rag_documents.json
Initializing embedding model: moka-ai/m3e-base
Loading M3E model: moka-ai/m3e-base on cpu...
Model loaded successfully (dimension: 768)
Collection 'project_slides' ready (count: 0)
Generating embeddings for 41 documents...
Inserting 41 documents into Chroma...
Insertion complete: 41 succeeded, 0 failed

Import complete:
  ✓ Inserted: 41
  ✗ Failed: 0
```

#### batch-import

Batch import all projects from ppt_outputs directory.

```bash
python -m src.scripts.vectordb_cli batch-import \
    --input-dir ppt_outputs \
    --collection project_slides
```

**Options**:
- `--input-dir`: Directory containing project outputs (required)
- `--collection`: Collection name (default: project_slides)
- `--config`: Config file path (default: config/settings.yaml)

**Behavior**:
- Searches for all `*/embeddings/rag_documents.json` files
- Imports each project sequentially
- Shows progress for each project
- Displays total statistics at the end

**Output**:
```
Found 3 projects to import
Initializing embedding model: moka-ai/m3e-base

Importing ChatBI...
  ✓ 41 documents

Importing ProductA...
  ✓ 35 documents

Importing ProductB...
  ✓ 28 documents

==================================================
Batch import complete:
  Total inserted: 104
  Total failed: 0
```

#### delete

Delete all documents for a specific project.

```bash
python -m src.scripts.vectordb_cli delete \
    --project ChatBI \
    --collection project_slides
```

**Options**:
- `--project`: Project name to delete (required)
- `--collection`: Collection name (default: project_slides)
- `--config`: Config file path (default: config/settings.yaml)

**Confirmation**: Prompts for confirmation before deletion.

**Output**:
```
Are you sure you want to delete this project? [y/N]: y
Deleted 41 documents for project 'ChatBI'
```

#### stats

Show collection statistics.

```bash
python -m src.scripts.vectordb_cli stats \
    --collection project_slides
```

**Options**:
- `--collection`: Collection name (default: project_slides)
- `--config`: Config file path (default: config/settings.yaml)

**Output**:
```
Collection: project_slides
Total documents: 104
Unique projects: 3

Projects:
  - ChatBI
  - ProductA
  - ProductB
```

#### query

Query the vector database with semantic search.

```bash
python -m src.scripts.vectordb_cli query \
    --text "ChatBI的核心功能是什么" \
    --top-k 5 \
    --project ChatBI
```

**Options**:
- `--text`: Query text (required)
- `--collection`: Collection name (default: project_slides)
- `--config`: Config file path (default: config/settings.yaml)
- `--top-k`: Number of results (default: 5)
- `--project`: Filter by project name (optional)

**Output**:
```
Initializing embedding model...
Loading M3E model: moka-ai/m3e-base on cpu...
Model loaded successfully (dimension: 768)
Collection 'project_slides' ready (count: 104)

Querying: 'ChatBI的核心功能是什么'
Filter: {'project_name': 'ChatBI'}

Found 5 results:

[1] ID: ChatBI_slide_005
    Distance: 0.2341
    Project: ChatBI
    Slide: 5
    Level: slide
    Text: 项目: ChatBI
页面标题: 核心功能
核心总结: ChatBI 提供自然语言问数、深度分析与智能归因等核心能力...

[2] ID: ChatBI_overview
    Distance: 0.3156
    Project: ChatBI
    Slide: 0
    Level: project
    Text: 项目综述: ChatBI
定位: 面向企业级的对话式商业智能平台...
```

#### list-projects

List all projects in the collection.

```bash
python -m src.scripts.vectordb_cli list-projects \
    --collection project_slides
```

**Options**:
- `--collection`: Collection name (default: project_slides)
- `--config`: Config file path (default: config/settings.yaml)

**Output**:
```
Projects in collection 'project_slides':
  - ChatBI
  - ProductA
  - ProductB

Total: 3 projects
```

## Common Use Cases

### Initial Setup

After running the pipeline for the first time, import documents:

```bash
# Single project
python -m src.scripts.vectordb_cli import \
    --input ppt_outputs/ChatBI/embeddings/rag_documents.json

# All projects
python -m src.scripts.vectordb_cli batch-import --input-dir ppt_outputs
```

### Rebuilding Index

To rebuild the index for a project:

```bash
# Delete old data
python -m src.scripts.vectordb_cli delete --project ChatBI

# Re-import
python -m src.scripts.vectordb_cli import \
    --input ppt_outputs/ChatBI/embeddings/rag_documents.json
```

### Testing Queries

Test semantic search before integrating into applications:

```bash
# Basic query
python -m src.scripts.vectordb_cli query --text "产品架构"

# Filtered query
python -m src.scripts.vectordb_cli query \
    --text "技术栈" \
    --project ChatBI \
    --top-k 3
```

### Monitoring

Check collection health and contents:

```bash
# Statistics
python -m src.scripts.vectordb_cli stats

# List projects
python -m src.scripts.vectordb_cli list-projects
```

## Configuration

All commands use settings from `config/settings.yaml` by default. Override with `--config`:

```bash
python -m src.scripts.vectordb_cli import \
    --input rag_documents.json \
    --config my_config.yaml
```

**Required Settings**:
- `embedding_model`: M3E model name
- `embedding_device`: cpu/cuda/mps
- `embedding_cache_dir`: Model cache directory
- `vectordb_persist_dir`: Chroma persistence directory

## Error Handling

### File Not Found

```
Error: Input file not found: ppt_outputs/Missing/embeddings/rag_documents.json
```

Solution: Check file path and ensure pipeline has run for the project.

### Model Download Failure

```
Error: Failed to load model moka-ai/m3e-base after 3 attempts: ...
```

Solution: Check internet connection or use a different model.

### Collection Not Found

```
Error: Collection 'wrong_name' not found
```

Solution: Use correct collection name or create it first with import command.

## Integration with Pipeline

The CLI tool complements the pipeline:

**Pipeline** (automatic):
- Runs during PPT processing
- Enabled via `vectordb_enabled: true` in config
- Inserts documents immediately after generation

**CLI Tool** (manual):
- Batch operations on existing documents
- Debugging and testing
- Re-indexing and cleanup
- Query testing

## Future Enhancements

- Progress bars for long operations (tqdm)
- Export command (dump collection to JSON)
- Reindex command (delete + import in one step)
- Backup and restore commands
- Collection comparison tool
- Query result export (CSV/JSON)
