# Embeddings Module (src/embeddings/)

Provides M3E Chinese embedding model integration for semantic text vectorization.

## Overview

This module wraps the M3E (Massive Mixed Embedding) Chinese text embedding model with automatic downloading, local caching, and efficient batch processing. M3E models are optimized for Chinese text and provide high-quality semantic representations for RAG applications.

## Key Components

### M3EEmbedding (m3e_model.py)

Wrapper class for M3E model with the following features:

**Automatic Model Management**:
- Downloads model from HuggingFace on first use
- Caches model locally in configurable directory
- Supports both m3e-base (768-dim) and m3e-large (1024-dim)

**Device Selection**:
- Supports CPU, CUDA (NVIDIA GPU), and MPS (Apple Silicon)
- Automatic fallback to CPU if requested device unavailable
- Warns user when falling back

**Batch Processing**:
- Efficient batch encoding with configurable batch size
- Progress bar for large batches (via tqdm)
- Automatic OOM handling (reduces batch size and retries)

**Error Handling**:
- Retry logic for model download failures (3 attempts with exponential backoff)
- OOM detection and automatic batch size reduction
- Clear error messages for debugging

## Usage

### Basic Usage

```python
from src.embeddings import M3EEmbedding

# Initialize model (downloads on first use)
model = M3EEmbedding(
    model_name="moka-ai/m3e-base",
    device="cpu",
    cache_dir="./models"
)

# Single text embedding
embedding = model.embed_single("这是一个测试文本")
print(f"Embedding shape: {embedding.shape}")  # (768,)

# Batch embedding
texts = ["文本1", "文本2", "文本3"]
embeddings = model.embed_texts(texts, batch_size=32)
print(f"Embeddings shape: {embeddings.shape}")  # (3, 768)
```

### With GPU

```python
# Use CUDA (NVIDIA GPU)
model = M3EEmbedding(device="cuda")

# Use MPS (Apple Silicon)
model = M3EEmbedding(device="mps")

# Larger batch size for GPU
embeddings = model.embed_texts(texts, batch_size=128)
```

### Model Selection

```python
# m3e-base: 768-dim, ~400MB, faster
model_base = M3EEmbedding(model_name="moka-ai/m3e-base")

# m3e-large: 1024-dim, ~1.2GB, more accurate
model_large = M3EEmbedding(model_name="moka-ai/m3e-large")
```

## Model Details

### m3e-base
- **Dimensions**: 768
- **Size**: ~400MB
- **Performance**: Balanced speed and accuracy
- **Recommended for**: Most use cases

### m3e-large
- **Dimensions**: 1024
- **Size**: ~1.2GB
- **Performance**: Higher accuracy, slower inference
- **Recommended for**: High-precision requirements

## Performance Considerations

### Batch Size Tuning

**CPU**:
- Recommended: 16-32
- Balance between speed and memory usage
- Typical speed: ~2-5 seconds per batch

**CUDA (GPU)**:
- Recommended: 64-128
- Utilize GPU memory efficiently
- Typical speed: 10-20x faster than CPU

**MPS (Apple Silicon)**:
- Recommended: 32-64
- Good balance for M1/M2/M3 chips
- Typical speed: 5-10x faster than CPU

### Memory Requirements

**m3e-base**:
- Model: ~400MB
- Runtime (CPU): ~1-2GB
- Runtime (GPU): ~2-4GB VRAM

**m3e-large**:
- Model: ~1.2GB
- Runtime (CPU): ~2-4GB
- Runtime (GPU): ~4-8GB VRAM

## Error Handling

### Model Download Failures

The module retries model downloads up to 3 times with exponential backoff:
- Attempt 1: Immediate
- Attempt 2: Wait 2 seconds
- Attempt 3: Wait 4 seconds

If all attempts fail, raises `RuntimeError` with details.

### Out of Memory (OOM)

When OOM occurs during batch processing:
1. Detects OOM error
2. Reduces batch size by 50%
3. Retries with smaller batch
4. Minimum batch size: 1

### Device Unavailable

If requested device is unavailable:
- Prints warning message
- Falls back to CPU automatically
- Continues processing

## Integration with Pipeline

The M3EEmbedding class is used by:
- `src/vectordb/chroma_store.py`: Generates embeddings for document insertion
- `src/pipeline.py`: Optionally embeds RAG documents during pipeline execution
- `src/scripts/vectordb_cli.py`: Embeds documents for standalone import

## Testing

Unit tests in `tests/test_embeddings.py` cover:
- Model initialization
- Single text embedding
- Batch text embedding
- Device selection and fallback
- OOM handling
- Model caching

## Dependencies

- `sentence-transformers>=2.3.0`: Model loading and inference
- `torch>=2.0.0`: PyTorch backend
- `numpy>=1.24.0`: Array operations
- `tqdm>=4.66.0`: Progress bars

## Future Enhancements

- Support for other Chinese embedding models (BGE, text2vec)
- Embedding caching (avoid re-embedding same texts)
- Quantization support (reduce model size)
- Batch size auto-tuning based on available memory
- Multi-GPU support for large-scale processing
