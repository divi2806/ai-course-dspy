from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"

    # LLM
    llm_provider: Literal["openai", "anthropic", "ollama"] = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    ollama_base_url: str = "http://localhost:11434"

    # Database
    database_url: str = "sqlite+aiosqlite:///./autocourse.db"

    # Vector store
    chroma_persist_dir: str = "./data/chroma"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        # Ensure asyncpg driver for postgres URLs that don't specify one
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.database_url

    @property
    def sync_database_url(self) -> str:
        """Synchronous DB URL for Alembic migrations."""
        url = self.database_url
        if "aiosqlite" in url:
            return url.replace("+aiosqlite", "")
        if "asyncpg" in url:
            return url.replace("+asyncpg", "+psycopg2")
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
