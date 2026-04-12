FROM python:3.13-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip nodejs npm ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Deno (required for DSPy RLM sandbox)
RUN curl -fsSL https://deno.land/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml README.md ./
RUN uv sync --no-dev

# Copy application
COPY app/ app/
COPY frontend/ frontend/

# Pre-install pyodide for DSPy RLM (avoids first-run download)
RUN PRIMITIVES_DIR=$(python -c "import dspy, pathlib; print(pathlib.Path(dspy.__file__).parent / 'primitives')") && \
    echo '{"dependencies":{"pyodide":"^0.27.0"}}' > "$PRIMITIVES_DIR/package.json" && \
    cd "$PRIMITIVES_DIR" && npm install --no-save && \
    deno run --node-modules-dir=auto \
        --allow-read="$PRIMITIVES_DIR/runner.js,$PRIMITIVES_DIR/node_modules" \
        "$PRIMITIVES_DIR/runner.js" || true

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
