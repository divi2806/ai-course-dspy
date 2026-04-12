# AutoCourse AI

An AI-powered course generation system. Give it a PDF, some text, a YouTube video, or just a topic you want to learn — and it builds a structured course with modules, explanations, analogies, real-world applications, common misconceptions, and a glossary. It then generates a STAR-format MCQ quiz so learners can test themselves on what they just read.

Built with FastAPI, DSPy RLM, and Perplexity for internet research.

---

## What it does

1. You bring in content — a PDF, raw text, YouTube video, or just a topic name.
2. The system stores the full text as a document and returns a `document_id`.
3. You call the generate-course endpoint. A DSPy RLM pipeline explores the document using an LLM + a sandboxed Python REPL (Deno + Pyodide), extracts key topics, and builds a structured course.
4. Each module in the course contains: learning objectives, a detailed explanation, analogies, examples, real-world applications, code snippets where relevant, common misconceptions, key takeaways, and a glossary.
5. You call the evaluate endpoint to generate MCQ questions. Each question follows the STAR schema — Situation, Task, Action (options), Result (explanation).

---

## Running locally (the quick way)

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — `pip install uv`
- [Deno](https://deno.land/) — `brew install deno` (macOS) or see deno.land for other platforms
- ffmpeg — only needed for YouTube ingestion (`brew install ffmpeg`)

### Setup

Clone the repo and copy the environment file:

```bash
cp .env.local .env
```

Open `.env` and fill in your API keys. At minimum you need an LLM provider key. See the LLM configuration section below.

Install dependencies:

```bash
uv sync
```

On first run, set up the Pyodide sandbox that DSPy RLM uses:

```bash
cd $(python -c "import dspy, pathlib; print(pathlib.Path(dspy.__file__).parent / 'primitives')")
echo '{"dependencies":{"pyodide":"^0.27.0"}}' > package.json
npm install
deno cache --node-modules-dir=auto runner.js
cd -
```

Start the server:

```bash
uv run uvicorn app.main:app --reload
```

Open your browser at **http://localhost:8000** to use the frontend. The API docs are at **http://localhost:8000/docs**.

---

## Running with Docker Compose

This is the recommended way if you want to share the project or run it on any machine without installing Python, Deno, or Node yourself. Docker Compose handles all of that.

### What Docker Compose does

When you run `docker compose up`, it reads `docker-compose.yml` and does the following:

1. Reads the `Dockerfile` and builds an image for the app. This installs Python, uv, Deno, Node/npm, all Python dependencies, and pre-installs the Pyodide sandbox so the RLM pipeline works without any extra setup steps.
2. Starts a container from that image with port 8000 exposed on your machine.
3. Reads your `.env` file and passes all the environment variables (API keys, database URL, etc.) into the container.
4. Mounts a Docker volume for the SQLite database so your data persists across restarts.
5. Runs a health check every 30 seconds so you can see when the app is ready.

### Steps

Make sure Docker Desktop is installed and running. Then:

```bash
# 1. Copy the environment file and fill in your API keys
cp .env.local .env
# Edit .env with your preferred editor and add your keys

# 2. Build and start everything
docker compose up
```

That is the entire setup. The first run will take a few minutes because it is building the image and installing dependencies. Subsequent runs start in seconds because Docker caches the layers.

Once running, open **http://localhost:8000** in your browser.

To run in the background:

```bash
docker compose up -d
```

To stop:

```bash
docker compose down
```

To stop and delete all data (including the database):

```bash
docker compose down -v
```

To rebuild after code changes:

```bash
docker compose up --build
```

### What the volumes do

The `docker-compose.yml` defines two mounts:

- `./data:/app/data` — maps the local `data/` folder into the container. If you ever use ChromaDB or store files locally, they go here.
- `db-data:/app/autocourse.db` — a named Docker volume for the SQLite database. Named volumes are managed by Docker and survive container restarts. Your generated courses and evaluations are stored here.

---

## LLM configuration

Set these in your `.env` file. Only one provider is active at a time.

**OpenCode Zen (recommended — access to many models via one key)**
```
LLM_PROVIDER=opencode
LLM_MODEL=kimi-k2.5
OPENCODE_API_KEY=sk-...
```

**Gemini**
```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=...
```

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

Install Ollama and pull a model first:
```bash
brew install ollama
ollama pull llama3.2
```

**Perplexity (for topic research only)**

Perplexity is used only by the `/ingest/topic` endpoint. It searches the internet and compiles a research report that becomes the source document for the course.

```
PERPLEXITY_API_KEY=pplx-...
```

---

## API endpoints

### Ingest

**POST /ingest/pdf** — upload a PDF file (multipart form)

**POST /ingest/text** — send raw text
```json
{ "text": "your content", "title": "optional" }
```

**POST /ingest/youtube** — provide a YouTube URL
```json
{ "url": "https://youtube.com/watch?v=...", "title": "optional" }
```

**POST /ingest/topic** — research a topic using Perplexity
```json
{
  "topic": "Transformer architecture in deep learning",
  "details": "Focus on how attention mechanisms replaced RNNs",
  "focus_areas": ["self-attention", "positional encoding", "BERT vs GPT"],
  "title": "optional"
}
```

All ingest endpoints return a `document_id`.

### Course generation

**POST /generate-course**
```json
{ "document_id": "...", "difficulty": "easy" }
```

`difficulty` must be `easy`, `medium`, or `hard`. Returns the full course including all modules.

**GET /course/{course_id}** — retrieve a previously generated course.

### Evaluation

**POST /evaluate**
```json
{ "course_id": "..." }
```

Generates STAR-format MCQ questions covering every module. The number of questions scales with module count — 4 per module for short courses, 2 per module for longer ones.

**GET /evaluate/{evaluation_id}** — retrieve a previously generated evaluation.

### Other

**GET /health** — returns `{ "status": "ok", "env": "development" }`

**GET /docs** — interactive Swagger UI for all endpoints.

---

## The RLM pipeline

Standard LLM pipelines for course generation split a document into chunks and summarise each chunk. This works for short documents but loses context for long books or videos — each chunk is processed in isolation, so cross-cutting themes and connections between sections are missed.

AutoCourse uses DSPy's RLM (Recursive Language Model) module instead. The LLM is given a sandboxed Python REPL and the full document text as a variable. It then runs multiple iterations:

- Iteration 1: prints the first few thousand characters to understand structure.
- Iterations 2-N: searches for specific topics, extracts quotes, stores findings per module.
- Final iteration: calls SUBMIT with the complete course JSON it has built across all iterations.

This means the LLM actively explores the document the way a human researcher would, rather than passively receiving pre-chunked fragments. For a 500-page book it can search by section, cross-reference topics, and pull specific passages per module.

The REPL sandbox is powered by Deno and Pyodide (Python running in WebAssembly inside Deno's secure runtime). This is why Deno is a requirement.

---

## STAR evaluation schema

MCQ questions are generated using the STAR framework:

- **Situation** — a realistic scenario placing the learner in a real context
- **Task** — what they need to figure out or decide in that situation
- **Action** — four options (A, B, C, D) representing possible responses
- **Result** — explanation of why the correct answer leads to the right outcome

This produces application-focused questions rather than recall questions. Instead of "What does ITC stand for?", a STAR question places the learner in a scenario where they have to apply their understanding of ITC to arrive at an answer.

---

## Database

SQLite is used by default. The database file `autocourse.db` is created automatically on first run. No migrations needed — tables are created on startup.

To use PostgreSQL:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/autocourse
```

When switching to PostgreSQL, run migrations with Alembic:
```bash
uv run alembic upgrade head
```

---

## Tests

Tests require no API keys and no external services. The LLM pipeline is fully mocked.

```bash
uv run pytest
```

Coverage reports are saved to `reports/coverage/index.html`.

---

## Project structure

```
app/
  main.py                         entry point, FastAPI app setup, frontend serving
  core/
    config.py                     all settings loaded from .env
    database.py                   async SQLAlchemy engine and session
  models/
    db.py                         Document, Course, Evaluation database models
    schemas.py                    Pydantic request and response types
  services/
    ingestion/
      pdf_ingester.py             extracts text from PDFs using PyMuPDF
      text_ingester.py            handles raw text input
      youtube_ingester.py         downloads and transcribes YouTube audio
      topic_ingester.py           researches topics via Perplexity sonar-pro
    pipeline/
      rlm_pipeline.py             DSPy RLM setup, CourseSignature, Deno interpreter
    course_generator.py           orchestrates pipeline, parses output, saves to DB
    evaluation_generator.py       generates STAR MCQs from course modules
  api/
    routes/
      ingest.py                   POST /ingest/pdf, /text, /youtube, /topic
      course.py                   POST /generate-course, GET /course/{id}
      evaluate.py                 POST /evaluate, GET /evaluate/{id}
frontend/
  index.html                      single-page UI for all endpoints
Dockerfile                        container image definition
docker-compose.yml                one-command local deployment
```
