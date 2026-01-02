# Tests Directory (tests/)

This directory contains automated tests for the PPT parsing and project profiling pipeline.

## Overview

The test suite covers unit tests for data models, integration tests for the full pipeline, and specialized tests for QA monitoring and caching functionality. Tests are designed to run both with and without external dependencies (LLM APIs, LibreOffice, Poppler).

## Test Files

### test_models.py

**Purpose**: Sanity checks for Pydantic data models

**Coverage**:
- `Manifest` model validation
- `ProjectProfile` model validation
- `PageSummary` model validation
- Field type checking and constraints
- Serialization/deserialization

**Dependencies**: None (pure Python)

**Usage**:
```bash
pytest tests/test_models.py -v
```

### test_pipeline_e2e.py

**Purpose**: End-to-end smoke test for the complete pipeline

**Coverage**:
- Full pipeline execution from PPTX to project profile
- Rendering (PPTX → PNG)
- Text extraction
- Page summarization (with mock LLM)
- Profile generation (with mock LLM)
- RAG document preparation
- Manifest generation

**Dependencies**:
- Sample PPTX: `ppts/ChatBI产品介绍_2025.pptx`
- LibreOffice (`soffice`) executable
- Poppler (`pdftoppm`) executable
- Mock LLM provider (no API calls)

**Skip Conditions**:
- Test is skipped if sample PPTX is missing
- Test is skipped if `soffice` or `pdftoppm` not found in PATH

**Configuration**:
- Uses `LLM_PROVIDER=mock` to avoid API calls
- Runs in isolated temporary directory
- Cleans up after execution

**Usage**:
```bash
# Run with mock LLM (no API calls)
pytest tests/test_pipeline_e2e.py -v

# Skip if dependencies missing
pytest tests/test_pipeline_e2e.py -v  # Auto-skips if soffice/pdftoppm missing
```

### test_qa_monitor.py

**Purpose**: Unit tests for QA monitoring and caching functionality

**Coverage**:
- Exact cache hit detection
- Cache expiration and TTL enforcement
- JSONL log writing
- Question normalization
- Cache key generation
- Semantic cache integration (optional)

**Dependencies**:
- Temporary directories for logs and cache
- Mock embedding model (for semantic cache tests)
- No external APIs required

**Usage**:
```bash
pytest tests/test_qa_monitor.py -v
```

### test_qa_cli_cache_smoke.py

**Purpose**: Smoke test for QA CLI cache hit indicators

**Coverage**:
- Cache hit message display (`[cache hit/<level>]`)
- CLI output formatting
- Integration with QAMonitor
- Dependency injection via monkeypatch

**Dependencies**:
- Uses monkeypatch to inject stub dependencies
- No external APIs or databases required

**Usage**:
```bash
pytest tests/test_qa_cli_cache_smoke.py -v
```

### tmp_run_tests.py

**Purpose**: Embedding regression and guardrail verification script

**Coverage**:
- `ChromaStore.query_with_guardrails` functionality
- Project filtering (single project scenario)
- Top-K recall (default: 8)
- Reranking with detail page/slide boosting
- Similarity threshold enforcement (tau=0.5)
- Output comparison for parameter tuning

**Output**: Generates `tests/tmp_embedding_test_round1.json` for comparison

**Dependencies**:
- Populated Chroma vector database
- M3E embedding model
- Real project data in `ppt_outputs/`

**Usage**:
```bash
# Run regression tests
python tests/tmp_run_tests.py

# Compare results
diff tests/tmp_embedding_test_round1.json tests/tmp_embedding_test_round2.json
```

**Note**: This is a manual regression test script, not part of the automated pytest suite.

## Running Tests

### All Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run with verbose output
pytest tests/ -vv
```

### Specific Test Files

```bash
# Models only
pytest tests/test_models.py -v

# Pipeline only
pytest tests/test_pipeline_e2e.py -v

# QA monitoring only
pytest tests/test_qa_monitor.py -v
```

### Skip Conditions

Tests automatically skip when dependencies are missing:

```bash
# test_pipeline_e2e.py skips if:
# - ppts/ChatBI产品介绍_2025.pptx not found
# - soffice not in PATH
# - pdftoppm not in PATH

# Manual skip
pytest tests/ -k "not e2e"  # Skip end-to-end tests
```

## Test Configuration

### Mock LLM Provider

For offline testing without API calls:

```yaml
# config/settings.yaml
llm_provider: mock
llm_model: mock-model
```

Mock mode returns the prompt as output, enabling full pipeline testing without external dependencies.

### Test Data

**Required Files**:
- `ppts/ChatBI产品介绍_2025.pptx`: Sample PPTX for smoke tests
- `config/settings.yaml`: Configuration file (can use mock settings)

**Generated Files** (cleaned up after tests):
- Temporary directories for test outputs
- Isolated from production `ppt_outputs/`

## Test Coverage

### Current Coverage

- **Models**: 100% (all Pydantic models validated)
- **Pipeline**: End-to-end smoke test with mock LLM
- **QA Monitoring**: Unit tests for caching and logging
- **QA CLI**: Smoke test for cache indicators

### Coverage Gaps

- Renderer module (requires external executables)
- Extractor module (covered indirectly via e2e)
- Summarizer module (covered indirectly via e2e with mock)
- Vector database operations (covered by tmp_run_tests.py)
- Embedding generation (covered by tmp_run_tests.py)

## Debugging Test Failures

### Pipeline E2E Test Fails

**Check Dependencies**:
```bash
# Verify executables
which soffice
which pdftoppm

# Test manually
soffice --version
pdftoppm -v
```

**Check Sample PPTX**:
```bash
# Verify file exists
ls -la ppts/ChatBI产品介绍_2025.pptx
```

**Check Configuration**:
```bash
# Verify mock mode
grep llm_provider config/settings.yaml  # Should be "mock"
```

### QA Monitor Tests Fail

**Check Permissions**:
- Ensure write access to `logs/qa_sessions/`
- Verify temporary directory creation

**Check Dependencies**:
- Ensure all required packages installed
- Verify Python version compatibility

### Embedding Tests Fail

**Check Vector Database**:
```bash
# Verify collection exists
python -m src.scripts.vectordb_cli stats
```

**Check Embedding Model**:
```bash
# Verify model cached
ls -la models/
```

## Adding New Tests

### Unit Test Template

```python
import pytest
from src.module import MyClass

def test_my_feature():
    """Test description"""
    obj = MyClass()
    result = obj.method()
    assert result == expected_value
```

### Integration Test Template

```python
import pytest
from pathlib import Path

@pytest.mark.skipif(
    not Path("required_file.txt").exists(),
    reason="Required file not found"
)
def test_integration():
    """Integration test description"""
    # Test implementation
    pass
```

### Fixture Template

```python
import pytest
from pathlib import Path
import tempfile

@pytest.fixture
def temp_output_dir():
    """Provide temporary output directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
```

## Continuous Integration

### CI Configuration

For CI/CD pipelines, ensure:
- LibreOffice and Poppler installed
- Sample PPTX file available
- Mock LLM mode enabled
- Sufficient disk space for temporary files

### CI Command

```bash
# Run tests suitable for CI
pytest tests/ -v --cov=src --cov-report=xml -k "not manual"
```

## Future Enhancements

- Add unit tests for renderer module (mock subprocess calls)
- Add unit tests for extractor module
- Add unit tests for summarizer module (mock LLM responses)
- Add performance benchmarks
- Add load tests for vector database
- Add integration tests for QA engine
- Add visual regression tests for rendered slides
- Add property-based tests (hypothesis)
