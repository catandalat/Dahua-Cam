from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select

from domain.db import SessionLocal, init_db
from domain.models import RawEvent, TrafficFlowSample, VehicleDetection, ViolationEvent
from domain.settings import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("retention")


async def run_retention(days: int | None = None) -> dict:
    settings = get_settings()
    days = days if days is not None else settings.retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    deleted = {"detections": 0, "violations": 0, "raw_events": 0, "flow": 0, "files": 0}

    async with SessionLocal() as db:
        # Collect image paths before delete
        dets = (
            await db.scalars(
                select(VehicleDetection).where(VehicleDetection.created_at < cutoff)
            )
        ).all()
        for d in dets:
            if d.image_paths:
                for p in d.image_paths.values():
                    fp = Path(str(p))
                    if fp.is_file():
                        fp.unlink(missing_ok=True)
                        deleted["files"] += 1

        r1 = await db.execute(
            delete(ViolationEvent).where(ViolationEvent.created_at < cutoff)
        )
        deleted["violations"] = r1.rowcount or 0
        r2 = await db.execute(
            delete(VehicleDetection).where(VehicleDetection.created_at < cutoff)
        )
        deleted["detections"] = r2.rowcount or 0
        r3 = await db.execute(delete(RawEvent).where(RawEvent.created_at < cutoff))
        deleted["raw_events"] = r3.rowcount or 0
        r4 = await db.execute(
            delete(TrafficFlowSample).where(TrafficFlowSample.created_at < cutoff)
        )
        deleted["flow"] = r4.rowcount or 0
        await db.commit()

    # Prune empty day dirs under snapshot_dir
    snap = Path(settings.snapshot_dir)
    if snap.exists():
        for day_dir in snap.iterdir():
            if day_dir.is_dir():
                try:
                    # remove empty nested dirs
                    for p in sorted(day_dir.rglob("*"), reverse=True):
                        if p.is_dir():
                            try:
                                p.rmdir()
                            except OSError:
                                pass
                    try:
                        day_dir.rmdir()
                    except OSError:
                        pass
                except OSError:
                    pass

    logger.info("Retention complete: %s", deleted)
    return deleted


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Purge old ANPR data and snapshots")
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args(argv)

    async def _run() -> None:
        await init_db()
        print(await run_retention(args.days))

    asyncio.run(_run())


if __name__ == "__main__":
    main()
