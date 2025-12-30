# Extractor Module

This module extracts text content from PPTX files using the python-pptx library.

## Purpose

Extract structured text from PowerPoint slides (titles, text frames, speaker notes) to complement visual analysis. This text provides context and reduces hallucination when LLMs analyze slide images.

## Architecture

### Single-Purpose Module

**`ppt_extractor.py`**:
- `extract_text(pptx_path: Path) -> List[SlideText]`
- Pure Python implementation (no external executables)
- Returns structured text per slide with consistent ordering

### Data Model

**`SlideText`** (defined in src/models.py):
```python
class SlideText(BaseModel):
    slide_no: int           # 1-indexed slide number
    title: Optional[str]    # Slide title (if present)
    text_content: str       # Concatenated text from all text frames
    notes: Optional[str]    # Speaker notes (if present)
```

## Design Decisions

**Why python-pptx?**
- Pure Python, no external dependencies
- Reliable text extraction from PPTX XML structure
- Widely used, well-maintained library
- Handles most PPTX variations gracefully

**Slide Ordering**:
- Relies on python-pptx's slide order (matches PowerPoint's slide sorter)
- Critical: Must align with rendered image order (001.png = slide 1)
- Validation: Compare slide count between extractor and renderer

**Text Concatenation**:
- All text frames concatenated with newlines
- Preserves reading order (top-to-bottom, left-to-right)
- No formatting preservation (plain text only)

**Speaker Notes**:
- Extracted separately from slide content
- Often contains additional context not visible on slide
- Used by LLM for richer understanding

## Usage Pattern

```python
from src.extractor import extract_text
from pathlib import Path

slide_texts = extract_text(Path("input.pptx"))

for slide_text in slide_texts:
    print(f"Slide {slide_text.slide_no}: {slide_text.title}")
    print(f"Content: {slide_text.text_content}")
    if slide_text.notes:
        print(f"Notes: {slide_text.notes}")
```

## Integration Points

**Called by**: `pipeline.py` (PPTPipeline.run)
**Depends on**: python-pptx library
**Outputs**: List of `SlideText` objects (in-memory, not persisted)

**Synchronization with Renderer**:
- Extractor and renderer must process same PPTX
- Slide numbers must align (slide_no=1 → 001.png)
- Pipeline validates: `len(slide_texts) == len(slide_images)`

## Error Handling

**Graceful Degradation**:
- Missing title → `title=None`
- No text frames → `text_content=""`
- No speaker notes → `notes=None`
- Empty slides are valid (not errors)

**Hard Failures**:
- File not found → raises `FileNotFoundError`
- Corrupted PPTX → raises `PackageNotFoundError` (from python-pptx)
- Invalid PPTX format → raises `ValueError`

## Common Tasks

### Debugging Text Extraction

1. Check slide count: `len(extract_text(pptx_path))`
2. Inspect specific slide: `slide_texts[0].model_dump()`
3. Verify alignment: Compare with rendered images
4. Check for empty content: `[s for s in slide_texts if not s.text_content]`

### Handling Special Cases

**Slides with only images**:
- `text_content=""` (empty string, not None)
- LLM relies entirely on visual analysis

**Slides with tables/charts**:
- python-pptx extracts text from table cells
- Chart data labels may be extracted
- Complex layouts may have unexpected text order

**Non-English text**:
- python-pptx handles Unicode correctly
- No special handling needed for Chinese, Japanese, etc.

## Testing

**Unit Tests**: `tests/test_models.py` validates `SlideText` schema
**Integration Tests**: `tests/test_pipeline_e2e.py` tests extraction with real PPTX

**Test Data**: Use `ppts/ChatBI产品介绍_2025.pptx` for smoke tests

## Limitations

**What This Module Does NOT Do**:
- Extract images or embedded objects
- Preserve formatting (bold, colors, fonts)
- Extract table structure (only cell text)
- Handle embedded videos or animations
- Process chart data (only visible labels)

For visual elements, rely on the renderer + LLM vision analysis.

## Future Enhancements

- Extract table structure (rows/columns)
- Preserve text formatting metadata
- Extract alt text from images
- Support for embedded Excel/Word objects
- Slide layout detection (title slide, content slide, etc.)
