# Gemini Context: Solution Advisor (PPT Parsing Pipeline)

## Project Overview
This project is a **PPT Parsing & Project Profiling Pipeline**. It converts project presentation slides (PPTX) into structured, traceable project profiles using multimodal Large Language Models (LLMs).

**Core Functionality:**
1.  **Rendering:** Converts PPTX slides into high-quality images (using LibreOffice).
2.  **Extraction:** Extracts raw text (titles, body, notes) from slides.
3.  **Page Summarization:** Uses Vision LLMs to analyze slide images and text to generate structured JSON summaries for each page.
4.  **Profile Generation:** Aggregates page summaries into a comprehensive project profile (positioning, core value, architecture, etc.) with evidence mapping.

## Technical Architecture

*   **Language:** Python 3.9+
*   **Frameworks:** Pydantic (Data Validation), LangChain (LLM interaction), Click (CLI), Pytest (Testing).
*   **Key Dependencies:**
    *   `python-pptx`: Text extraction.
    *   `LibreOffice` (headless) & `Poppler`: Rendering slides to images.
    *   `OpenAI` / `Anthropic` (via LangChain): LLM processing.

### Directory Structure
*   `src/`: Main source code.
    *   `renderer/`: Handles PPTX -> PDF -> Image conversion.
    *   `extractor/`: Extracts text content from PPTX.
    *   `summarizer/`: LLM client, page summarizer, and profile generator logic.
    *   `models.py`: Pydantic data models (`PageSummary`, `ProjectProfile`, `Manifest`).
    *   `pipeline.py`: Main orchestration logic.
    *   `config.py`: Environment configuration management.
*   `docs/`: Project documentation and design specs.
*   `ppts/`: Input directory for PPTX files.
*   `ppt_outputs/`: Output directory for generated artifacts (images, JSONs).
*   `tests/`: Automated tests (unit and e2e).

## Setup & Configuration

### Prerequisites
1.  **Python 3.9+**
2.  **LibreOffice:** Must be installed and accessible via `soffice` (or configured in `.env`).
3.  **Poppler:** Must be installed (provides `pdftoppm`).

### Installation
```bash
pip install -r requirements.txt
```

### Configuration (`.env`)
Create a `.env` file based on `.env.example`:
```ini
LLM_PROVIDER=openai  # or 'mock' for testing
LLM_API_KEY=sk-...
LLM_BASE_URL=...
LLM_MODEL=gpt-4-vision-preview
LIBREOFFICE_PATH=/usr/bin/soffice
```

## Usage

### Running the Pipeline
```bash
python -m src --input ppts/your_presentation.pptx --output ppt_outputs/your_output_folder
```
**Options:**
*   `--force`: Force re-execution even if the input file hash hasn't changed.
*   `--verbose`: Enable verbose logging.

### Outputs
The pipeline generates the following in the output directory:
*   `slides/`: PNG images of each slide.
*   `page_summaries/`: Individual JSON summaries for each slide.
*   `doc_summary/project_profile.json`: aggregated project profile.
*   `manifest.json`: Execution metadata and error logs.

## Development

### Testing
Run all tests:
```bash
pytest
```
*Note: Tests requiring LibreOffice or LLM credentials will skip if not available/configured.*

### Code Style
*   **Formatting:** `black src/ tests/`
*   **Linting:** `ruff check src/ tests/`

### Conventions
*   **Commit Messages:** Concise, imperative mood (e.g., "Add renderer retry logic"). Often in Chinese per existing history.
*   **File Naming:** Snake case for Python files.
*   **Error Handling:** Fail fast on critical errors; log and continue for single-page errors (recorded in `manifest.json`).
