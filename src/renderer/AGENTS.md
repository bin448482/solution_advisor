# Agent Notes for `src/renderer/`

Role: render PPTX to PNG slides.

- `base.py`: abstract `Renderer` + `RenderError`.
- `libreoffice.py`: `LibreOfficeRenderer` uses `soffice --headless --convert-to pdf` then `pdftoppm -png -r <dpi>`; renames to `001.png`... under target directory.
- Dependencies: executables `soffice` and `pdftoppm` must be in PATH or configured via `Settings`.
