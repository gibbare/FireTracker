"""Main ingestion pipeline: fetch → cluster → persist."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Fire, RawDetection, IngestionLog
from worker.firms import fetch_detections, FirmsError
from worker.clustering import build_fire_clusters

logger = logging.getLogger(__name__)

_HAVERSINE_THRESHOLD_DEG = settings.cluster_radius_km / 111.0  # rough degrees


async def run_ingestion(db: AsyncSession) -> None:
    """Fetch FIRMS data, cluster, and upsert fires. Logs result to DB."""
    attempted_at = datetime.now(timezone.utc)
    log = IngestionLog(
        attempted_at=attempted_at,
        succeeded=False,
    )

    try:
        if not settings.firms_map_key:
            raise FirmsError(
                "401",
                "FIRMS_MAP_KEY is not set. Set the environment variable to enable data fetching.",
            )

        raw = fetch_detections(
            map_key=settings.firms_map_key,
            source=settings.firms_source,
            area=settings.firms_area,
            day_range=min(settings.firms_day_range, 5),
        )

        fires = build_fire_clusters(
            raw,
            radius_km=settings.cluster_radius_km,
            time_gap_hours=settings.cluster_time_gap_hours,
            active_threshold_hours=settings.active_threshold_hours,
        )

        updated = await _upsert_fires(db, fires)

        log.succeeded = True
        log.detections_fetched = len(raw)
        log.fires_updated = updated
        logger.info("Ingestion succeeded: %d detections → %d fires", len(raw), updated)

    except FirmsError as exc:
        log.error_code = exc.code
        log.error_message = exc.message
        log.human_explanation = exc.human
        logger.error("Ingestion failed [%s]: %s", exc.code, exc.message)

    except Exception as exc:
        log.error_code = "unknown"
        log.error_message = str(exc)
        log.human_explanation = f"Oväntat fel: {exc}"
        logger.exception("Ingestion failed unexpectedly")

    db.add(log)
    await db.commit()


async def _upsert_fires(db: AsyncSession, fires: list[dict]) -> int:
    """Upsert clustered fires; try to match existing fires by proximity."""
    updated_count = 0

    for fire_data in fires:
        points = fire_data.pop("points")
        existing = await _find_nearby_fire(
            db, fire_data["latitude"], fire_data["longitude"], fire_data["first_seen"]
        )

        if existing:
            # Merge: extend time range, increase detection count
            if fire_data["first_seen"] < existing.first_seen:
                existing.first_seen = fire_data["first_seen"]
            if fire_data["last_seen"] > existing.last_seen:
                existing.last_seen = fire_data["last_seen"]
            existing.duration_hours = (
                existing.last_seen - existing.first_seen
            ).total_seconds() / 3600
            existing.detections += fire_data["detections"]
            existing.max_frp = max(existing.max_frp or 0, fire_data["max_frp"])
            existing.status = fire_data["status"]
            fire_id = existing.fire_id
        else:
            new_fire = Fire(**fire_data)
            db.add(new_fire)
            await db.flush()
            fire_id = new_fire.fire_id

        for pt in points:
            db.add(
                RawDetection(
                    fire_id=fire_id,
                    latitude=pt["latitude"],
                    longitude=pt["longitude"],
                    acq_datetime=pt["acq_datetime"],
                    confidence=pt.get("confidence"),
                    frp=pt.get("frp"),
                    source=pt.get("source"),
                )
            )
        updated_count += 1

    await db.commit()
    return updated_count


async def _find_nearby_fire(
    db: AsyncSession, lat: float, lon: float, first_seen: datetime
) -> Fire | None:
    """Find an existing fire within ~cluster_radius_km and within time gap."""
    from datetime import timedelta

    time_cutoff = first_seen - timedelta(hours=settings.cluster_time_gap_hours)
    result = await db.execute(
        select(Fire).where(
            Fire.last_seen >= time_cutoff,
            Fire.latitude.between(lat - _HAVERSINE_THRESHOLD_DEG, lat + _HAVERSINE_THRESHOLD_DEG),
            Fire.longitude.between(lon - _HAVERSINE_THRESHOLD_DEG, lon + _HAVERSINE_THRESHOLD_DEG),
        )
    )
    candidates = result.scalars().all()
    if not candidates:
        return None
    # Return closest
    from worker.clustering import _haversine_rad
    return min(candidates, key=lambda f: _haversine_rad(f.latitude, f.longitude, lat, lon))
