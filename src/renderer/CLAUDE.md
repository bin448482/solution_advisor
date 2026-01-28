# Renderer Module

This module handles the conversion of PPTX/PDF files into PNG slide images for visual analysis.

## Purpose

Convert PowerPoint presentations (PPTX) and PDFs into high-quality PNG images, one per page, enabling multimodal LLM analysis of slide content including visual elements, layouts, and formatting that text extraction alone cannot capture.

## Architecture

### Two-Step Conversion Strategy

**PPTX → PDF → PNG** (via LibreOffice headless)

This approach provides better reliability than direct PPTX-to-image conversion:
1. LibreOffice converts PPTX to PDF (preserves layout and formatting)
2. Poppler's `pdftoppm` converts PDF pages to PNG images
3. Intermediate PDF is retained for debugging purposes

**PDF → PNG** (via Poppler `pdftoppm` only)

When input is PDF, the renderer skips LibreOffice and renders directly with Poppler.

### Key Components

**`base.py`**:
- `Renderer` (abstract base class): Defines the rendering interface
- `RenderError`: Custom exception for rendering failures
- Contract: `render(pptx_path, output_dir, dpi) -> List[Path]`

**`libreoffice.py`**:
- `LibreOfficeRenderer`: Concrete implementation using LibreOffice + Poppler; supports direct PDF rendering via `pdftoppm`
- Dependencies: `soffice` (LibreOffice) and `pdftoppm` (Poppler) executables
- Output naming: `001.png`, `002.png`, ... (zero-padded 3 digits)

## Design Decisions

**Why LibreOffice?**
- Widely available, open-source, cross-platform
- Excellent PPTX compatibility (better than most Python libraries)
- Headless mode suitable for server environments

**Why intermediate PDF?**
- More reliable than direct image conversion
- PDF preserved for debugging and manual inspection
- Enables future alternative rendering paths

**Why Poppler (pdftoppm)?**
- Fast, lightweight, battle-tested
- High-quality rasterization with configurable DPI
- Better than ImageMagick for PDF rendering

**Sequential Processing**:
- LibreOffice doesn't support parallel conversion
- Each PPTX is processed sequentially
- Trade-off: reliability over speed for this step

## Configuration

Controlled via `Settings` (src/config.py):
- `libreoffice_path`: Path to `soffice` executable (default: "soffice")
- `pdftoppm_path`: Path to `pdftoppm` executable (default: "pdftoppm")
- `render_dpi`: Output image resolution (default: 150)

Higher DPI = better quality but larger files and slower processing.

## Usage Pattern

```python
from src.renderer import LibreOfficeRenderer
from src.config import Settings

settings = Settings.from_yaml()
renderer = LibreOfficeRenderer(settings)

# Render all slides to output_dir/slides/ (PPTX)
slide_paths = renderer.render(
    pptx_path=Path("input.pptx"),
    output_dir=Path("output"),
    dpi=150
)
# Returns: [output/slides/001.png, output/slides/002.png, ...]

# Render all pages to output_dir/slides/ (PDF)
slide_paths = renderer.render(
    pptx_path=Path("input.pdf"),
    output_dir=Path("output"),
    dpi=150
)
```

## Error Handling

**Fail Fast**:
- Missing executables → `RenderError` immediately
- Invalid PPTX → `RenderError` with details
- Conversion failures → `RenderError` with command output

**No Partial Results**:
- If any slide fails, entire rendering fails
- Ensures consistency (all slides or none)

## Integration Points

**Called by**: `pipeline.py` (PPTPipeline.run)
**Depends on**: External executables (soffice, pdftoppm)
**Outputs to**: `<output_dir>/slides/` directory

## Common Tasks

### Adding a New Renderer

1. Subclass `Renderer` in `base.py`
2. Implement `render()` method
3. Handle errors with `RenderError`
4. Update `pipeline.py` to use new renderer

### Debugging Rendering Issues

1. Check intermediate PDF: `<output_dir>/slides/<basename>.pdf`
2. Verify executables: `soffice --version`, `pdftoppm -v`
3. Test manually: `soffice --headless --convert-to pdf input.pptx`
4. Check DPI setting (too high may cause memory issues)

### Optimizing Performance

- DPI: Lower for faster processing (100-150 sufficient for most LLMs)
- Disk I/O: Use SSD for output directory
- LibreOffice: Ensure no GUI instances running (conflicts with headless)

## Testing

See `tests/test_pipeline_e2e.py` for integration tests that exercise the renderer with real PPTX files.

**Mock Testing**: Not applicable (requires real executables)
**Smoke Test**: Requires LibreOffice and Poppler installed

## Future Enhancements

- Support for alternative renderers (e.g., unoconv, direct Python libraries)
- Parallel processing via multiple LibreOffice instances
- Caching of intermediate PDFs across runs
- Support for other input formats (PPT, ODP)
