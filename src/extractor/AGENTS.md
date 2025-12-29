# Agent Notes for `src/extractor/`

Role: extract slide text from PPTX.

- `ppt_extractor.py`: uses `python-pptx` to pull title, text frames, notes per slide; returns `SlideText` list.
- No external binaries; relies on consistent slide order to align with rendered images.
