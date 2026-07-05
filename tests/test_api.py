"""Tests for REST API endpoints."""

import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.models import Fire, IngestionLog


def _make_fire(**kwargs) -> Fire:
    defaults = dict(
        fire_id="test-id-001",
        latitude=61.0,
        longitude=15.0,
        first_seen=datetime(2024, 7, 10, 12, 0, tzinfo=timezone.utc),
        last_seen=datetime(2024, 7, 15, 12, 0, tzinfo=timezone.utc),
        duration_hours=120.0,
        detections=10,
        max_frp=25.5,
        status="active",
    )
    defaults.update(kwargs)
    return Fire(**defaults)


@pytest.mark.asyncio
async def test_list_fires_empty(client):
    resp = await client.get("/fires")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_list_fires_returns_geojson(client, db_session):
    db_session.add(_make_fire())
    await db_session.commit()

    resp = await client.get("/fires")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    feat = data["features"][0]
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Point"
    assert "fire_id" in feat["properties"]
    assert "first_seen" in feat["properties"]
    assert "last_seen" in feat["properties"]


@pytest.mark.asyncio
async def test_list_fires_filter_active(client, db_session):
    db_session.add(_make_fire(fire_id="a1", status="active"))
    db_session.add(_make_fire(fire_id="a2", status="inactive"))
    await db_session.commit()

    resp = await client.get("/fires?status=active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["features"][0]["properties"]["status"] == "active"


@pytest.mark.asyncio
async def test_list_fires_filter_inactive(client, db_session):
    db_session.add(_make_fire(fire_id="b1", status="active"))
    db_session.add(_make_fire(fire_id="b2", status="inactive"))
    await db_session.commit()

    resp = await client.get("/fires?status=inactive")
    data = resp.json()
    assert data["count"] == 1
    assert data["features"][0]["properties"]["status"] == "inactive"


@pytest.mark.asyncio
async def test_get_fire_by_id(client, db_session):
    db_session.add(_make_fire(fire_id="specific-id"))
    await db_session.commit()

    resp = await client.get("/fires/specific-id")
    assert resp.status_code == 200
    data = resp.json()
    assert data["properties"]["fire_id"] == "specific-id"
    assert "raw_detections" in data["properties"]


@pytest.mark.asyncio
async def test_get_fire_not_found(client):
    resp = await client.get("/fires/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "fire_count" in data


@pytest.mark.asyncio
async def test_ingestion_log_structure(client, db_session):
    db_session.add(IngestionLog(
        attempted_at=datetime(2024, 7, 15, 12, 0, tzinfo=timezone.utc),
        succeeded=True,
        detections_fetched=5,
        fires_updated=2,
    ))
    await db_session.commit()

    resp = await client.get("/ingestion-log")
    assert resp.status_code == 200
    data = resp.json()
    assert "data_stale" in data
    assert "last_success" in data
    assert "entries" in data
    assert len(data["entries"]) == 1
    entry = data["entries"][0]
    assert entry["succeeded"] is True
    assert entry["detections_fetched"] == 5


@pytest.mark.asyncio
async def test_ingestion_log_stale_when_no_success(client, db_session):
    db_session.add(IngestionLog(
        attempted_at=datetime(2024, 7, 15, 12, 0, tzinfo=timezone.utc),
        succeeded=False,
        error_code="401",
        error_message="Unauthorized",
        human_explanation="MAP_KEY är ogiltig.",
    ))
    await db_session.commit()

    resp = await client.get("/ingestion-log")
    data = resp.json()
    assert data["data_stale"] is True
    assert data["last_success"] is None


@pytest.mark.asyncio
async def test_list_fires_bbox_filter(client, db_session):
    db_session.add(_make_fire(fire_id="c1", latitude=61.0, longitude=15.0))
    db_session.add(_make_fire(fire_id="c2", latitude=55.0, longitude=13.0))
    await db_session.commit()

    resp = await client.get("/fires?bbox=14,60,16,62")
    data = resp.json()
    assert data["count"] == 1
    assert data["features"][0]["properties"]["fire_id"] == "c1"
