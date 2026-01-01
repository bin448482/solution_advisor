"""
Centralized prompt loader for the solution advisor project.

Prompts are stored as UTF-8 `.txt` files in this directory to keep editing simple
and avoid shipping descriptive Markdown to the model. Accessors below cache the
contents to avoid repeat disk reads in hot paths.
"""

from functools import lru_cache
from pathlib import Path

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


__all__ = [
    "get_qa_prompt",
    "get_page_summary_prompt",
    "get_project_profile_prompt",
]
