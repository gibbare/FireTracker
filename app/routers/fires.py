from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Fire, RawDetection

router = APIRouter(prefix="/fires", tags=["fires"])


def _fire_to_feature(fire: Fire, include_detections: bool = False) -> dict:
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [fire.longitude, fire.latitude],
        },
        "properties": {
            "fire_id": fire.fire_id,
            "first_seen": fire.first_seen.isoformat(),
            "last_seen": fire.last_seen.isoformat(),
            "duration_hours": fire.duration_hours,
            "detections": fire.detections,
            "max_frp": fire.max_frp,
            "status": fire.status,
            "bbox": [fire.min_lon, fire.min_lat, fire.max_lon, fire.max_lat]
            if fire.min_lat is not None
            else None,
        },
    }
    if include_detections:
        feature["properties"]["raw_detections"] = [
            {
                "lat": d.latitude,
                "lon": d.longitude,
                "time": d.acq_datetime.isoformat(),
                "confidence": d.confidence,
                "frp": d.frp,
            }
            for d in (fire.raw_detections or [])
        ]
    return feature


@router.get("")
async def list_fires(
    status: Optional[str] = Query(None, description="active or inactive"),
    bbox: Optional[str] = Query(None, description="west,south,east,north"),
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if status:
        filters.append(Fire.status == status)
    if bbox:
        try:
            west, south, east, north = map(float, bbox.split(","))
        except ValueError:
            raise HTTPException(400, "bbox must be west,south,east,north floats")
        filters.extend(
            [
                Fire.longitude >= west,
                Fire.longitude <= east,
                Fire.latitude >= south,
                Fire.latitude <= north,
            ]
        )
    if from_dt:
        filters.append(Fire.last_seen >= from_dt)
    if to_dt:
        filters.append(Fire.first_seen <= to_dt)

    stmt = select(Fire)
    if filters:
        stmt = stmt.where(and_(*filters))
    stmt = stmt.order_by(Fire.last_seen.desc()).limit(2000)

    result = await db.execute(stmt)
    fires = result.scalars().all()

    return {
        "type": "FeatureCollection",
        "features": [_fire_to_feature(f) for f in fires],
        "count": len(fires),
    }


@router.get("/{fire_id}")
async def get_fire(fire_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Fire)
        .options(selectinload(Fire.raw_detections))
        .where(Fire.fire_id == fire_id)
    )
    fire = result.scalar_one_or_none()
    if fire is None:
        raise HTTPException(404, "Fire not found")
    return _fire_to_feature(fire, include_detections=True)
