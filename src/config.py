from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, Field


class QAMonitoringSettings(BaseModel):
    monitor_enabled: bool = Field(default=True)
    monitor_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    log_dir: str = Field(default="logs/qa_sessions")


class QACacheSettings(BaseModel):
    cache_enabled: bool = Field(default=True)
    cache_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    cache_ttl_days: int = Field(default=7, ge=1)
    cache_backend: str = Field(default="jsonl")
    cache_semantic_enabled: bool = Field(default=True)
    cache_semantic_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    cache_collection: str = Field(default="qa_cache")
    cache_persist_dir: str = Field(default="./chroma_db")
    vectordb_version: str | int = Field(default="v1")


class QASettings(BaseModel):
    monitor: QAMonitoringSettings = Field(default_factory=QAMonitoringSettings)
    cache: QACacheSettings = Field(default_factory=QACacheSettings)


class Settings(BaseModel):
    """Application configuration loaded from a YAML file."""

    llm_provider: str = Field(default="openai")
    llm_api_key: str | None = Field(default=None)
    llm_base_url: str | None = Field(default=None)
    llm_model: str = Field(default="gpt-4-vision-preview")
    llm_temperature: float = Field(default=0.1)

    render_dpi: int = Field(default=150)
    max_workers: int = Field(default=3)
    libreoffice_path: str = Field(default="soffice")
    pdftoppm_path: str = Field(default="pdftoppm")

    # Vector Database Configuration
    vectordb_enabled: bool = Field(default=False)
    vectordb_provider: str = Field(default="chroma")
    vectordb_persist_dir: str = Field(default="./chroma_db")
    vectordb_collection_name: str = Field(default="project_slides")

    # Embedding Configuration
    embedding_model: str = Field(default="moka-ai/m3e-base")
    embedding_device: str = Field(default="cpu")
    embedding_batch_size: int = Field(default=32)
    embedding_cache_dir: str = Field(default="./models")

    # QA Monitor & Cache
    qa: QASettings = Field(default_factory=QASettings)

    @classmethod
    def from_yaml(cls, path: Path | str = Path("config/settings.yaml")) -> "Settings":
        """Load settings from YAML; raise if missing to avoid silent defaults."""

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"Config file not found: {path}. Copy config/settings.example.yaml and fill in secrets."
            )

        data: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(**data)

    def with_overrides(self, **kwargs) -> "Settings":
        """Return a copy with runtime overrides (used by CLI)."""
        data = self.model_dump()
        data.update(kwargs)
        return Settings(**data)


def default_output_dir(pptx_path: Path) -> Path:
    """Default snapshot directory beside the PPT under ppt_outputs/."""
    base = Path("ppt_outputs")
    return base / pptx_path.stem
