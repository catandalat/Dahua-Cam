from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from domain.settings import get_settings

_settings = get_settings()
engine = create_async_engine(_settings.database_url, pool_pre_ping=True, pool_size=10)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from domain.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migrations for already-running DBs
        alters = [
            "ALTER TABLE traffic_flow_samples ADD COLUMN IF NOT EXISTS direction VARCHAR(64)",
            "ALTER TABLE vehicle_detections ADD COLUMN IF NOT EXISTS vehicle_class VARCHAR(32)",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS map_icon VARCHAR(32) DEFAULT 'camera'",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS map_note VARCHAR(256)",
            "ALTER TABLE vehicle_sessions ADD COLUMN IF NOT EXISTS entry_speed DOUBLE PRECISION",
            "ALTER TABLE vehicle_sessions ADD COLUMN IF NOT EXISTS exit_speed DOUBLE PRECISION",
        ]
        for stmt in alters:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass
