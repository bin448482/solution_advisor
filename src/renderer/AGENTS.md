# Agent Notes for `src/renderer/`

Role: render PPTX/PDF to PNG slides.

- `base.py`: abstract `Renderer` + `RenderError`.
- `libreoffice.py`: `LibreOfficeRenderer` supports PPTX (soffice → PDF → pdftoppm) and direct PDF rendering via `pdftoppm`; renames to `001.png`... under target directory.
- Dependencies: executables `soffice` and `pdftoppm` must be in PATH or configured via `Settings`.
