"""M3E Chinese embedding model wrapper with caching and batch processing."""

import time
from pathlib import Path
from typing import List

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from tqdm import tqdm


class M3EEmbedding:
    """M3E embedding model wrapper with local caching and batch processing.

    Supports automatic model download from HuggingFace, device selection (CPU/CUDA/MPS),
    and efficient batch processing with progress tracking.
    """

    def __init__(
        self,
        model_name: str = "moka-ai/m3e-base",
        device: str = "cpu",
        cache_dir: str = "./models",
    ):
        """Initialize M3E model with auto-download and caching.

        Args:
            model_name: HuggingFace model ID (m3e-base or m3e-large)
            device: Device to run on (cpu, cuda, mps)
            cache_dir: Directory to cache downloaded models
        """
        self.model_name = model_name
        self.device = self._select_device(device)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.model = self._load_model()

    def _select_device(self, requested_device: str) -> str:
        """Select device with fallback to CPU if requested device unavailable."""
        if requested_device == "cuda" and not torch.cuda.is_available():
            print(f"Warning: CUDA requested but not available, falling back to CPU")
            return "cpu"
        if requested_device == "mps" and not torch.backends.mps.is_available():
            print(f"Warning: MPS requested but not available, falling back to CPU")
            return "cpu"
        return requested_device

    def _load_model(self) -> SentenceTransformer:
        """Load model with retry logic for download failures."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"Loading M3E model: {self.model_name} on {self.device}...")
                model = SentenceTransformer(
                    self.model_name,
                    cache_folder=str(self.cache_dir),
                    device=self.device,
                )
                print(f"Model loaded successfully (dimension: {model.get_sentence_embedding_dimension()})")
                return model
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Model load failed (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(
                        f"Failed to load model {self.model_name} after {max_retries} attempts: {e}"
                    )

    def embed_texts(
        self, texts: List[str], batch_size: int = 32, show_progress: bool = True
    ) -> np.ndarray:
        """Generate embeddings for a list of texts with batching.

        Args:
            texts: List of text strings to embed
            batch_size: Batch size for processing
            show_progress: Whether to show progress bar

        Returns:
            numpy array of shape (len(texts), embedding_dim)
        """
        if not texts:
            return np.array([])

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                convert_to_numpy=True,
            )
            return embeddings
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                # OOM error: reduce batch size and retry
                new_batch_size = max(1, batch_size // 2)
                print(f"OOM error: reducing batch size from {batch_size} to {new_batch_size}")
                return self.embed_texts(texts, batch_size=new_batch_size, show_progress=show_progress)
            raise

    def embed_single(self, text: str) -> np.ndarray:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed

        Returns:
            numpy array of shape (embedding_dim,)
        """
        return self.model.encode(text, convert_to_numpy=True)

    @property
    def dimension(self) -> int:
        """Return embedding dimension (768 for m3e-base, 1024 for m3e-large)."""
        return self.model.get_sentence_embedding_dimension()
