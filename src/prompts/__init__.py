"""
Centralized prompt loader for the solution advisor project.

Prompts are stored as UTF-8 `.txt` files in this directory to keep editing simple
and avoid shipping descriptive Markdown to the model. Accessors below cache the
contents to avoid repeat disk reads in hot paths.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def _load(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8").strip()


def get_qa_prompt() -> str:
    """RAG 问答主提示（包含 {context}/{question} 占位符）。"""
    return _load("qa_zh")


def get_page_summary_prompt() -> str:
    """单页总结提示。"""
    return _load("page_summary_zh")


def get_project_profile_prompt() -> str:
    """项目画像生成提示。"""
    return _load("project_profile_zh")


def get_guided_templates(path: str | Path | None = None) -> Dict[str, Any]:
    """加载引导式对话的模板配置（YAML）。"""
    if path is None:
        path = PROMPTS_DIR / "guided_templates.yaml"
    else:
        path = Path(path)
        if not path.is_absolute():
            # 允许相对路径或只给文件名
            candidate = PROMPTS_DIR / path
            if candidate.exists():
                path = candidate
    if not path.exists():
        raise FileNotFoundError(f"guided templates not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


__all__ = [
    "get_qa_prompt",
    "get_page_summary_prompt",
    "get_project_profile_prompt",
    "get_guided_templates",
]
