from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import IngestionLog, Fire

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count()).select_from(Fire))
    fire_count = result.scalar()
    return {"status": "ok", "fire_count": fire_count}


@router.get("/ingestion-log")
async def ingestion_log(db: AsyncSession = Depends(get_db), limit: int = 50):
    result = await db.execute(
        select(IngestionLog).order_by(IngestionLog.attempted_at.desc()).limit(limit)
    )
    entries = result.scalars().all()

    last_success = None
    for e in entries:
        if e.succeeded:
            last_success = e.attempted_at
            break

    now = datetime.now(timezone.utc)
    data_stale = False
    if last_success is None or (now - last_success) > timedelta(hours=12):
        data_stale = True

    return {
        "data_stale": data_stale,
        "last_success": last_success.isoformat() if last_success else None,
        "entries": [
            {
                "id": e.id,
                "attempted_at": e.attempted_at.isoformat(),
                "succeeded": e.succeeded,
                "error_code": e.error_code,
                "error_message": e.error_message,
                "human_explanation": e.human_explanation,
                "detections_fetched": e.detections_fetched,
                "fires_updated": e.fires_updated,
            }
            for e in entries
        ],
    }
