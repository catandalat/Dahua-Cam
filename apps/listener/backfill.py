from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from dahua_client.client import DahuaClient
from dahua_client.kv_parser import kv_lines_to_dict
from domain.db import SessionLocal, init_db
from domain.models import Camera, RawEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")


async def backfill_camera(camera_id: UUID, hours: float = 2.0) -> dict:
    async with SessionLocal() as db:
        cam = await db.get(Camera, camera_id)
        if not cam:
            raise SystemExit(f"Camera {camera_id} not found")

    client = DahuaClient(
        cam.host, cam.username, cam.password, port=cam.port, use_https=cam.use_https
    )
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    fmt = "%Y-%m-%d %H:%M:%S"
    start_s = start.strftime(fmt)
    end_s = end.strftime(fmt)

    finder = await client.media_find_create()
    logger.info("Created finder %s for %s", finder, cam.name)
    try:
        await client.media_find_file(finder, start_time=start_s, end_time=end_s)
        total = 0
        while True:
            text = await client.media_find_next(finder, count=50)
            data = kv_lines_to_dict(text)
            found = int(data.get("found", 0) or 0)
            if found <= 0:
                break
            async with SessionLocal() as db:
                db.add(
                    RawEvent(
                        camera_id=cam.id,
                        event_code="MediaBackfill",
                        event_utc=datetime.now(timezone.utc),
                        payload={"finder": finder, "batch": data},
                        image_paths=None,
                    )
                )
                await db.commit()
            total += found
            if found < 50:
                break
        return {"camera_id": str(camera_id), "items": total}
    finally:
        try:
            await client.media_find_close(finder)
            await client.media_find_destroy(finder)
        except Exception as exc:
            logger.warning("Cleanup finder failed: %s", exc)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Backfill TrafficCar media find results")
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--hours", type=float, default=2.0)
    args = parser.parse_args(argv)

    async def _run() -> None:
        await init_db()
        result = await backfill_camera(UUID(args.camera_id), hours=args.hours)
        print(result)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
