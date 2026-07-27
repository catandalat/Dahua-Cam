from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://anpr:anpr@localhost:5432/anpr"
    database_url_sync: str = "postgresql://anpr:anpr@localhost:5432/anpr"
    redis_url: str = "redis://localhost:6379/0"
    snapshot_dir: str = "./data/snapshots"
    session_overstay_hours: float = 24.0
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    log_level: str = "INFO"
    retention_days: int = 30
    live_channel: str = "anpr:live"
    ingest_stream: str = "anpr:ingest"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
