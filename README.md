# AutoCourse AI

A backend system that turns raw content into structured courses. You give it a PDF, some text, or a YouTube link and it produces a course broken into modules with explanations, examples, code snippets, and key takeaways. You choose the difficulty level — easy, medium, or hard — and the system adapts the depth of content accordingly.

Built with FastAPI, DSPy, and ChromaDB.

---

## How it works

1. You send content to one of the ingest endpoints (PDF upload, raw text, or YouTube URL).
2. The system extracts text, splits it into chunks, embeds them, and stores everything in ChromaDB.
3. You call the generate-course endpoint with the document ID and a difficulty level.
4. A five-stage DSPy pipeline runs: it cleans the text, extracts topics, breaks down concepts, filters by difficulty, and builds the final course.
5. The course is saved to the database and returned.

---

## Requirements

- Python 3.11 or higher
- uv (package manager)
- An LLM — OpenAI, Anthropic, or a local Ollama model
- ffmpeg (only needed for YouTube ingestion)

---

## Setup

Copy the example environment file and fill in your values:

```
cp .env.example .env
```

The only value you must set is your LLM credentials. Everything else has sensible defaults.

Install dependencies:

```
uv sync
```

Start the server:

```
uv run uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000. Interactive docs are at http://localhost:8000/docs.

---

## LLM configuration

The system supports three providers. Set these in your `.env` file.

**OpenAI**
```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

**Anthropic**
```
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-5-haiku-20241022
ANTHROPIC_API_KEY=sk-ant-...
```

**Ollama (local, free)**
```
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
```

For Ollama, install it separately and pull a model first:
```
brew install ollama
ollama pull llama3.2
```

---

## API

### Ingest content

**POST /ingest/text** — send raw text
```json
{
  "text": "your content here",
  "title": "optional title"
}
```

**POST /ingest/pdf** — upload a PDF file (multipart form)

**POST /ingest/youtube** — provide a YouTube video or playlist URL
```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "title": "optional title"
}
```

All three return a `document_id` you use in the next step.

### Generate a course

**POST /generate-course**
```json
{
  "document_id": "the id from ingest",
  "difficulty": "easy"
}
```

`difficulty` must be one of `easy`, `medium`, or `hard`.

### Retrieve a course

**GET /course/{course_id}**

Returns the full course with all modules.

---

## Database

SQLite is used by default and requires no setup. A file called `autocourse.db` is created automatically in the project root on first run.

To use PostgreSQL instead, update `DATABASE_URL` in your `.env`:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/autocourse
```

When using PostgreSQL, run migrations with Alembic:
```
uv run alembic upgrade head
```

---

## Tests

### Running the tests

Tests require no API keys, no running database, and no external services. Everything is mocked.

```
uv run pytest
```

Coverage reports are saved to `reports/coverage/index.html` after each run. Open it in a browser to see line-by-line coverage.

---

### What was tested — 28 tests, all passing

#### Chunker (5 tests) — `tests/test_ingestion.py`

The chunker splits text into overlapping word-budget windows. These tests verify the core splitting logic works correctly before anything touches an LLM or database.

| Test | What it checks |
|---|---|
| `test_basic_split` | Text longer than the chunk size produces multiple chunks, none exceeding the word budget |
| `test_overlap_carries_words` | The tail of one chunk appears at the head of the next, confirming overlap works |
| `test_single_short_text` | Text shorter than the chunk size comes back as a single unchanged chunk |
| `test_empty_text_returns_empty` | Empty input returns an empty list, no crash |
| `test_very_long_single_sentence` | A sentence longer than the chunk size is hard-split rather than dropped |

#### Text ingester (5 tests) — `tests/test_ingestion.py`

Tests the raw text ingestion path end to end, from input string to `IngestedContent` object.

| Test | What it checks |
|---|---|
| `test_returns_ingested_content` | A valid text input produces a correct `IngestedContent` with `source_type=text` and at least one chunk |
| `test_default_title` | When no title is given, it defaults to "Untitled Document" |
| `test_empty_text_raises` | Whitespace-only input raises a `ValueError` with a clear message |
| `test_source_ref_is_raw` | The `source_ref` field is set to `"raw"` for text inputs |
| `test_chunk_count_matches` | The number of chunks reported matches the actual list length |

#### PDF ingester (2 tests) — `tests/test_ingestion.py`

| Test | What it checks |
|---|---|
| `test_missing_file_raises` | A path that does not exist raises `FileNotFoundError` |
| `test_valid_pdf` | A real PDF created in the test is ingested and produces at least one chunk with the correct `source_type` |

#### DSPy pipeline (5 tests) — `tests/test_pipeline.py`

The LLM is fully mocked here. Each DSPy `ChainOfThought` step is replaced with a `MagicMock` so the logic of the pipeline can be tested without any API calls.

| Test | What it checks |
|---|---|
| `test_pipeline_produces_course` | All five pipeline stages are called in order and the final output is a correctly shaped course dict |
| `test_parse_modules_valid` | A well-formed list of module dicts is converted into validated `Module` objects |
| `test_parse_modules_skips_malformed` | A malformed module in the list is silently skipped without crashing the whole response |
| `test_safe_parse_json_strips_fences` | LLM output wrapped in markdown code fences (```json ... ```) is correctly unwrapped and parsed |
| `test_safe_parse_json_returns_fallback_on_invalid` | Completely invalid JSON returns the specified fallback value instead of raising an exception |

#### API endpoints (11 tests) — `tests/test_api.py`

Full end-to-end integration tests using an in-memory SQLite database and an HTTP test client. The vector store and LLM pipeline are mocked so no external services are needed.

| Test | What it checks |
|---|---|
| `test_health` | `GET /health` returns 200 with `status: ok` |
| `test_ingest_text_success` | `POST /ingest/text` with valid text returns 201, a `document_id`, correct `source_type`, and chunk count |
| `test_ingest_text_too_short` | Text under 50 characters is rejected with 422 at the schema level |
| `test_ingest_text_empty` | Text that is only whitespace is rejected with 400 |
| `test_ingest_pdf_wrong_extension` | Uploading a non-PDF file to `POST /ingest/pdf` returns 422 |
| `test_ingest_pdf_success` | A real PDF file created in the test is accepted and returns 201 with `source_type: pdf` |
| `test_generate_course_success` | Full ingest → generate flow returns 201 with correct `document_id`, `difficulty`, `title`, and modules |
| `test_generate_course_unknown_document` | Generating a course for a non-existent document ID returns 404 |
| `test_generate_course_invalid_difficulty` | A difficulty value outside easy/medium/hard returns 422 |
| `test_get_course_success` | Full ingest → generate → retrieve flow: the saved course is returned correctly by its ID |
| `test_get_course_not_found` | Fetching a course with an unknown ID returns 404 |

---

### What is not tested and why

| Area | Why it is not covered |
|---|---|
| YouTube ingestion | Requires yt-dlp to download real audio and Whisper to transcribe it. Both need network access and significant runtime. The service code is written and works but is excluded from automated tests. |
| Real LLM responses | The DSPy pipeline stages are all mocked. Testing with a real LLM would require an API key, cost money, produce non-deterministic outputs, and make tests slow and flaky. |
| ChromaDB vector operations | The vector store is mocked in all tests via `conftest.py`. Real ChromaDB tests would require the full embedding model to be loaded on every test run. |
| PostgreSQL-specific behaviour | All tests run against SQLite. Behaviour that differs between databases (e.g. enum handling, concurrent writes) is not covered. |
| Alembic migrations | Migration scripts are not tested. They should be verified manually against a real PostgreSQL instance before deploying. |

---

### Coverage summary

After the last run:

```
Total coverage: 69%

100%  app/models/db.py
100%  app/models/schemas.py
100%  app/services/ingestion/text_ingester.py
 88%  app/services/ingestion/pdf_ingester.py
 85%  app/main.py
 82%  app/core/config.py
 82%  app/utils/chunker.py
 75%  app/api/routes/course.py
 75%  app/services/pipeline/course_pipeline.py
 21%  app/services/ingestion/youtube_ingester.py   (no real YouTube tests)
 40%  app/services/vector_store.py                 (mocked in all tests)
 40%  app/services/course_generator.py             (LLM call is mocked)
 57%  app/core/database.py                         (real DB init not exercised)
```

The low-coverage files are intentional — they are the parts that require live external services (LLM, ChromaDB, YouTube). The application logic that can be verified without those services sits at or above 75%.

---

## Project structure

```
app/
  main.py                      entry point, app setup
  core/
    config.py                  all settings loaded from .env
    database.py                async SQLAlchemy engine and session
  models/
    db.py                      Document and Course database models
    schemas.py                 Pydantic request and response types
  services/
    ingestion/
      pdf_ingester.py          extracts text from PDFs using PyMuPDF
      text_ingester.py         handles raw text input
      youtube_ingester.py      downloads and transcribes YouTube audio
    pipeline/
      signatures.py            DSPy typed signatures for each pipeline stage
      course_pipeline.py       the CoursePipeline module and LLM setup
    vector_store.py            ChromaDB wrapper for storing and retrieving chunks
    course_generator.py        orchestrates pipeline, persistence, and response
  api/
    routes/
      ingest.py                POST /ingest/pdf, /text, /youtube
      course.py                POST /generate-course, GET /course/{id}
  utils/
    chunker.py                 sentence-aware sliding window text chunker
tests/
  conftest.py                  shared fixtures, in-memory DB, mocked vector store
  test_ingestion.py            unit tests for chunker and ingesters
  test_pipeline.py             unit tests for DSPy pipeline with mocked LLM
  test_api.py                  integration tests for all endpoints
```
