from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

from domain.settings import get_settings


class LiveBus:
    def __init__(self, url: str | None = None):
        self.url = url or get_settings().redis_url
        self._redis: redis.Redis | None = None

    async def connect(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(self.url, decode_responses=True)
        return self._redis

    async def publish(self, payload: dict[str, Any]) -> None:
        settings = get_settings()
        r = await self.connect()
        await r.publish(settings.live_channel, json.dumps(payload, default=str))

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


live_bus = LiveBus()
