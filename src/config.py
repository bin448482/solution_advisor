from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment or .env."""

    llm_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices("LLM_PROVIDER", "OPENAI_PROVIDER"),
    )
    llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"),
    )
    llm_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_BASE_URL", "OPENAI_BASE_URL"),
    )
    llm_model: str = Field(
        default="gpt-4-vision-preview",
        validation_alias=AliasChoices("LLM_MODEL", "OPENAI_MODEL"),
    )
    llm_temperature: float = Field(
        default=0.1,
        validation_alias=AliasChoices("LLM_TEMPERATURE", "OPENAI_TEMPERATURE"),
    )

    render_dpi: int = Field(default=150, alias="RENDER_DPI")
    max_workers: int = Field(default=3, alias="MAX_WORKERS")
    libreoffice_path: str = Field(default="soffice", alias="LIBREOFFICE_PATH")
    pdftoppm_path: str = Field(default="pdftoppm", alias="PDFTOPPM_PATH")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def with_overrides(self, **kwargs) -> "Settings":
        """Return a copy with runtime overrides (used by CLI)."""
        data = self.model_dump()
        data.update(kwargs)
        return Settings(**data)


def default_output_dir(pptx_path: Path) -> Path:
    """Default snapshot directory beside the PPT under ppt_outputs/."""
    base = Path("ppt_outputs")
    return base / pptx_path.stem
