import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.course import router as course_router
from app.api.routes.evaluate import router as evaluate_router
from app.api.routes.ingest import router as ingest_router
from app.core.config import get_settings
from app.core.database import init_db

settings = get_settings()

logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
)
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.dev.ConsoleRenderer() if settings.app_env == "development"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting AutoCourse AI", env=settings.app_env)
    await init_db()
    log.info("Database initialised")
    yield


app = FastAPI(
    title="AutoCourse AI",
    description=(
        "AI-powered multi-modal course generation. "
        "Ingest PDFs, text, and YouTube content then generate structured "
        "courses at easy, medium, or hard difficulty using DSPy."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router)
app.include_router(course_router)
app.include_router(evaluate_router)


@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


_FRONTEND = Path(__file__).parent.parent / "frontend"
if _FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend() -> FileResponse:
        return FileResponse(str(_FRONTEND / "index.html"))
