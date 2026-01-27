from pathlib import Path
from typing import List

from src.utils import command_exists, ensure_dir, run_command

from .base import RenderError, Renderer


def _sorted_by_index(paths: List[Path]) -> List[Path]:
    def key(p: Path) -> int:
        stem = p.stem.split("-")[-1]
        try:
            return int(stem)
        except ValueError:
            return 0

    return sorted(paths, key=key)


class LibreOfficeRenderer(Renderer):
    def __init__(self, libreoffice_path: str, pdftoppm_path: str, dpi: int = 150) -> None:
        self.libreoffice_path = libreoffice_path
        self.pdftoppm_path = pdftoppm_path
        self.dpi = dpi

    def render(self, pptx_path: Path, output_dir: Path) -> List[Path]:
        if not command_exists(self.libreoffice_path):
            raise RenderError(f"LibreOffice executable not found: {self.libreoffice_path}")
        if not command_exists(self.pdftoppm_path):
            raise RenderError(f"pdftoppm executable not found: {self.pdftoppm_path}")

        ensure_dir(output_dir)
        for png in output_dir.glob("*.png"):
            png.unlink()

        pdf_path = output_dir / f"{pptx_path.stem}.pdf"
        if pdf_path.exists():
            pdf_path.unlink()

        # 1) PPTX -> PDF
        run_command(
            [
                self.libreoffice_path,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(pptx_path),
            ],
            cwd=pptx_path.parent,
        )
        if not pdf_path.exists():
            raise RenderError(f"PDF not generated: {pdf_path}")

        return self._render_pdf_to_png(pdf_path, output_dir)

    def render_pdf(self, pdf_path: Path, output_dir: Path) -> List[Path]:
        if not command_exists(self.pdftoppm_path):
            raise RenderError(f"pdftoppm executable not found: {self.pdftoppm_path}")

        ensure_dir(output_dir)
        for png in output_dir.glob("*.png"):
            png.unlink()

        return self._render_pdf_to_png(pdf_path, output_dir)

    def _render_pdf_to_png(self, pdf_path: Path, output_dir: Path) -> List[Path]:
        # PDF -> PNG
        prefix = output_dir / "slide"
        run_command(
            [
                self.pdftoppm_path,
                "-png",
                "-r",
                str(self.dpi),
                str(pdf_path),
                str(prefix),
            ],
            cwd=output_dir,
        )

        generated = _sorted_by_index(list(output_dir.glob("slide-*.png")))
        if not generated:
            raise RenderError("No PNG files produced by pdftoppm")

        slides: List[Path] = []
        for idx, src in enumerate(generated, start=1):
            dest = output_dir / f"{idx:03d}.png"
            if dest.exists():
                dest.unlink()
            src.rename(dest)
            slides.append(dest)

        return slides
