from abc import ABC, abstractmethod
from pathlib import Path
from typing import List


class RenderError(RuntimeError):
    """Raised when rendering fails."""


class Renderer(ABC):
    @abstractmethod
    def render(self, pptx_path: Path, output_dir: Path) -> List[Path]:
        """Render PPTX to a list of slide image paths."""
