"""Tests for error handling in the ingestion pipeline."""

import pytest
import pytest_asyncio
import respx
import httpx
from datetime import datetime, timezone

from sqlalchemy import select
from app.models import IngestionLog
from worker.ingestion import run_ingestion


@pytest.mark.asyncio
@respx.mock
async def test_failed_ingestion_logs_error(db_session, monkeypatch):
    """A 401 from FIRMS should produce a failed IngestionLog entry."""
    from app import config as cfg
    monkeypatch.setattr(cfg.settings, "firms_map_key", "BADKEY")

    respx.get("https://firms.modaps.eosdis.nasa.gov/api/area/csv/BADKEY/VIIRS_SNPP_NRT/4,54,32,71/3").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )

    await run_ingestion(db_session)

    result = await db_session.execute(select(IngestionLog).order_by(IngestionLog.id.desc()))
    log = result.scalars().first()

    assert log is not None
    assert log.succeeded is False
    assert log.error_code == "401"
    assert log.human_explanation is not None
    assert "MAP_KEY" in log.human_explanation


@pytest.mark.asyncio
@respx.mock
async def test_successful_ingestion_logs_ok(db_session, monkeypatch):
    from app import config as cfg
    monkeypatch.setattr(cfg.settings, "firms_map_key", "GOODKEY")

    sample_csv = (
        "latitude,longitude,brightness,scan,track,acq_date,acq_time,"
        "satellite,instrument,confidence,version,bright_t31,frp,daynight\n"
        "61.1,15.2,310,0.39,0.36,2024-07-15,0845,N,VIIRS,nominal,2.0NRT,287,12.5,D\n"
    )
    respx.get("https://firms.modaps.eosdis.nasa.gov/api/area/csv/GOODKEY/VIIRS_SNPP_NRT/4,54,32,71/3").mock(
        return_value=httpx.Response(200, text=sample_csv)
    )

    await run_ingestion(db_session)

    result = await db_session.execute(select(IngestionLog).order_by(IngestionLog.id.desc()))
    log = result.scalars().first()

    assert log is not None
    assert log.succeeded is True
    assert log.detections_fetched == 1
    assert log.fires_updated == 1


@pytest.mark.asyncio
async def test_missing_map_key_logs_error(db_session, monkeypatch):
    """Missing MAP_KEY should produce a 401-like log entry."""
    from app import config as cfg
    monkeypatch.setattr(cfg.settings, "firms_map_key", "")

    await run_ingestion(db_session)

    result = await db_session.execute(select(IngestionLog).order_by(IngestionLog.id.desc()))
    log = result.scalars().first()

    assert log is not None
    assert log.succeeded is False
    assert log.error_code == "401"


@pytest.mark.asyncio
@respx.mock
async def test_timeout_logs_correct_code(db_session, monkeypatch):
    from app import config as cfg
    monkeypatch.setattr(cfg.settings, "firms_map_key", "K")

    respx.get("https://firms.modaps.eosdis.nasa.gov/api/area/csv/K/VIIRS_SNPP_NRT/4,54,32,71/3").mock(
        side_effect=httpx.TimeoutException("timed out")
    )

    await run_ingestion(db_session)

    result = await db_session.execute(select(IngestionLog).order_by(IngestionLog.id.desc()))
    log = result.scalars().first()

    assert log.succeeded is False
    assert log.error_code == "timeout"
    assert "timeout" in log.human_explanation.lower() or "svarar inte" in log.human_explanation
