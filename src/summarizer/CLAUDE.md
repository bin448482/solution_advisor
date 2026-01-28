# Summarizer Module

This module uses LLMs to analyze slides and generate structured summaries and project profiles.

## Purpose

Transform raw slide content (images + text, or image-only for PDF) into structured, semantic summaries using multimodal LLMs. Aggregates page-level summaries into comprehensive project profiles with evidence traceability.

## Architecture

### Three-Layer Design

**`llm_client.py`**: LLM API abstraction
- Wraps LangChain chat models (OpenAI, Anthropic, local models)
- Supports vision (image analysis) via data URLs
- Mock mode for offline testing

**`page_summarizer.py`**: Single-slide analysis
- Fuses slide image + extracted text
- Generates structured `PageSummary` with confidence scoring
- Parallel processing across slides

**`profile_generator.py`**: Multi-slide aggregation
- Synthesizes all page summaries into `ProjectProfile`
- Builds evidence map (field → slide numbers)
- Sequential processing (requires all summaries)

## Key Components

### LLMClient (llm_client.py)

**Purpose**: Unified interface for different LLM providers

**Supported Providers**:
- `openai`: OpenAI API (GPT-4 Vision, GPT-4o, etc.)
- `anthropic`: Anthropic API (Claude 3.5 Sonnet, etc.)
- `local`: Local models via LangChain
- `mock`: Returns prompt as output (no API call)

**Configuration** (via Settings):
```python
llm_provider: str       # "openai" | "anthropic" | "local" | "mock"
llm_api_key: str        # API key (not needed for mock)
llm_base_url: str       # Custom endpoint (optional)
llm_model: str          # Model name
llm_temperature: float  # 0.0-1.0 (default: 0.1 for consistency)
```

**Vision Support**:
- Accepts image as data URL (base64-encoded PNG)
- Automatically includes in message content for vision models
- Falls back to text-only if image not provided

**Mock Mode**:
- Set `llm_provider: mock` for testing without API
- Returns the prompt text as output
- Enables pipeline testing without external dependencies

### PageSummarizer (page_summarizer.py)

**Purpose**: Analyze individual slides and generate structured summaries

**Input**:
- Slide image (PNG file path)
- Extracted text (`SlideText` object, optional for PDF image-only)
- Slide number

**Output**: `PageSummary` object with:
- `slide_no`, `title`, `one_liner` (≤30 chars)
- `bullets` (3-7 key points)
- `details` (1-2 paragraph elaboration)
- `image_caption` (optional visual description)
- `entities` (products, modules, customers, metrics)
- `signals` (page type: positioning, architecture, features, cases, etc.)
- `evidence` (source slide numbers)
- `confidence` (0-1, for quality flagging)

**Prompt Strategy**:
- Chinese instructions for Chinese-language PPTs
- Explicit JSON schema with examples
- Emphasizes confidence scoring for uncertain extractions
- Requests visual grounding via image_caption
- Image-only mode when `slide_text` is None (PDF input); prompt excludes text and emphasizes visible content only

**Error Handling**:
- JSON parsing with fallbacks (handles dict or list responses)
- Retries on API errors (3x with exponential backoff)
- Returns partial summary on parse failure (better than nothing)

### ProfileGenerator (profile_generator.py)

**Purpose**: Aggregate page summaries into comprehensive project profile

**Input**: List of all `PageSummary` objects

**Output**: `ProjectProfile` object with:
- Core: project_name, positioning, target_users, core_value, core_capabilities
- Technical: architecture, deployment, integrations
- Competitive: differentiators, cases
- Boundaries: risks_and_limits, open_questions
- **evidence_map**: Maps each field to source slide numbers

**Prompt Strategy**:
- Synthesizes information across all slides
- Identifies patterns and themes
- Resolves conflicts (e.g., different positioning statements)
- Cites evidence for every claim (slide numbers)

**Evidence Map**:
- Critical for traceability
- Format: `{"positioning": [1, 3], "core_value": [2, 5, 8]}`
- Enables verification and drill-down

## Design Decisions

**Why LangChain?**
- Unified interface across providers
- Built-in retry logic and error handling
- Easy to swap models without code changes

**Why Structured Output (JSON)?**
- Enables downstream processing (RAG, search, filtering)
- Reduces ambiguity in LLM responses
- Facilitates validation and quality checks

**Why Confidence Scoring?**
- Flags low-quality extractions for manual review
- Helps prioritize human verification efforts
- Improves over time as patterns emerge

**Why Chinese Prompts?**
- Better results for Chinese-language content
- Reduces translation errors and ambiguity
- Matches target user base

**Parallel Page Summarization**:
- Slides are independent → can process in parallel
- Configurable via `max_workers` (default: 3)
- Trade-off: Speed vs. API rate limits

**Sequential Profile Generation**:
- Requires all summaries → must be sequential
- Synthesis step needs global context
- Relatively fast (single LLM call)

## Usage Patterns

### Basic Page Summarization

```python
from src.summarizer import PageSummarizer, LLMClient
from src.config import Settings

settings = Settings.from_yaml()
client = LLMClient(settings)
summarizer = PageSummarizer(client)

summary = summarizer.summarize_page(
    slide_image_path=Path("slides/001.png"),
    slide_text=slide_text,
    slide_no=1
)

# PDF image-only usage (no SlideText)
summary = summarizer.summarize_page(
    slide_image_path=Path("slides/001.png"),
    slide_text=None,
    slide_no=1
)
```

### Profile Generation

```python
from src.summarizer import ProfileGenerator

generator = ProfileGenerator(client)
profile = generator.generate_profile(page_summaries)

# Check evidence
print(profile.evidence_map["positioning"])  # [1, 3]
```

### Mock Mode Testing

```python
# In settings.yaml:
# llm_provider: mock

# LLMClient will return prompts as output
# Enables testing without API calls
```

## Integration Points

**Called by**: `pipeline.py` (PPTPipeline.run)
**Depends on**:
- LLM API (OpenAI/Anthropic/local)
- src/models.py (PageSummary, ProjectProfile)
- src/utils.py (image_to_data_url)

**Outputs**:
- PageSummary objects (saved to page_summaries/*.json)
- ProjectProfile object (saved to doc_summary/project_profile.json)

## Error Handling

**API Errors**:
- Retry 3x with exponential backoff
- Log error details
- Raise exception if all retries fail

**JSON Parse Errors**:
- Attempt multiple parsing strategies
- Fall back to partial extraction
- Log warning and continue

**Low Confidence**:
- Not an error, but flagged in summary
- Recorded in manifest for review
- Processing continues normally

## Common Tasks

### Debugging Summarization Issues

1. Check prompt: Use mock mode to see exact prompt sent
2. Inspect raw response: Add logging in llm_client.py
3. Validate JSON: Check page_summaries/*.json files
4. Review confidence: `[s for s in summaries if s.confidence < 0.5]`

### Improving Summary Quality

1. Adjust temperature (lower = more consistent)
2. Refine prompts (add examples, clarify instructions)
3. Use better models (GPT-4o > GPT-4 Vision)
4. Increase context (include more extracted text)

### Handling API Rate Limits

1. Reduce `max_workers` (fewer parallel requests)
2. Add delays between requests
3. Use local models (no rate limits)
4. Batch process during off-peak hours

## Testing

**Mock Mode**: Set `llm_provider: mock` for offline testing
**Integration Tests**: `tests/test_pipeline_e2e.py` with mock provider
**Manual Testing**: Use real API with small PPT samples

## Future Enhancements

- Support for streaming responses (faster feedback)
- Caching of LLM responses (avoid re-processing)
- Multi-model ensemble (combine outputs from different models)
- Fine-tuned models for specific domains
- Automatic prompt optimization based on feedback
