from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage

from src.config import Settings
from src.utils import encode_image_to_data_url


class LLMClient:
    """Thin wrapper around LangChain chat models."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.llm_provider.lower()
        self._client = self._build_client()

    @property
    def is_mock(self) -> bool:
        return self.provider in {"mock", "none"}

    def _build_client(self):
        if self.is_mock:
            return None

        if self.provider in {"openai", "local"}:
            from langchain_openai import ChatOpenAI

            api_key = self.settings.llm_api_key or "EMPTY"
            return ChatOpenAI(
                api_key=api_key,
                model=self.settings.llm_model,
                temperature=self.settings.llm_temperature,
                base_url=self.settings.llm_base_url,
            )

        if self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            if not self.settings.llm_api_key:
                raise ValueError("LLM_API_KEY is required for Anthropic provider")
            return ChatAnthropic(
                api_key=self.settings.llm_api_key,
                model=self.settings.llm_model,
                temperature=self.settings.llm_temperature,
            )

        raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def generate(self, prompt: str, image_path: Optional[Path] = None) -> str:
        if self.is_mock:
            return prompt

        if self.provider in {"openai", "local"}:
            content = [{"type": "text", "text": prompt}]
            if image_path:
                content.append({"type": "image_url", "image_url": {"url": encode_image_to_data_url(image_path)}})
            messages = [HumanMessage(content=content)]
        else:
            # Fall back to text-only; add image path hint for non-vision providers
            text_prompt = prompt
            if image_path:
                text_prompt += f"\n[Image path: {image_path}]"
            messages = [HumanMessage(content=text_prompt)]

        response = self._client.invoke(messages)
        raw = response.content
        if isinstance(raw, list):
            text_parts = []
            for part in raw:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                else:
                    text_parts.append(str(part))
            return "\n".join(filter(None, text_parts))
        return str(raw)
