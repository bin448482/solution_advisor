from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, Field


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
