"""Tests for fire clustering logic."""

from datetime import datetime, timezone, timedelta
import pytest
from worker.clustering import build_fire_clusters, _haversine_rad


def dt(offset_hours=0):
    return datetime(2024, 7, 15, 12, 0, tzinfo=timezone.utc) + timedelta(hours=offset_hours)


def det(lat, lon, offset_hours=0, frp=10.0):
    return {"latitude": lat, "longitude": lon, "acq_datetime": dt(offset_hours), "frp": frp, "confidence": "nominal", "source": "VIIRS"}


# ── Haversine ──────────────────────────────────────────────────────────────────
def test_haversine_zero():
    assert _haversine_rad(60, 15, 60, 15) == pytest.approx(0.0)


def test_haversine_known():
    # Stockholm to Gothenburg ≈ 400 km
    dist = _haversine_rad(59.33, 18.07, 57.71, 11.97)
    assert 380 < dist < 430


# ── Spatial grouping ──────────────────────────────────────────────────────────
def test_nearby_points_clustered():
    detections = [
        det(61.000, 15.000),
        det(61.010, 15.010),  # ~1.1 km away
        det(61.005, 15.005),  # within radius
    ]
    fires = build_fire_clusters(detections, radius_km=2.0, time_gap_hours=48)
    assert len(fires) == 1
    assert fires[0]["detections"] == 3


def test_distant_points_separate():
    detections = [
        det(61.000, 15.000),
        det(65.000, 20.000),  # far away
    ]
    fires = build_fire_clusters(detections, radius_km=2.0, time_gap_hours=48)
    assert len(fires) == 2


def test_just_outside_radius_separate():
    # ~2.5 km apart — outside 2 km radius
    detections = [
        det(61.000, 15.000),
        det(61.023, 15.000),  # ~2.6 km
    ]
    fires = build_fire_clusters(detections, radius_km=2.0, time_gap_hours=48)
    assert len(fires) == 2


# ── Time gap splitting ─────────────────────────────────────────────────────────
def test_time_gap_creates_separate_fire():
    detections = [
        det(61.000, 15.000, offset_hours=0),
        det(61.001, 15.001, offset_hours=1),   # same spatial cluster
        det(61.000, 15.000, offset_hours=60),  # 59h later → new fire
        det(61.001, 15.001, offset_hours=61),
    ]
    fires = build_fire_clusters(detections, radius_km=2.0, time_gap_hours=48)
    assert len(fires) == 2


def test_no_time_gap_single_fire():
    detections = [
        det(61.000, 15.000, offset_hours=0),
        det(61.001, 15.001, offset_hours=24),  # 24h gap, within threshold
        det(61.001, 15.001, offset_hours=47),  # 47h total — still within 48h gap
    ]
    fires = build_fire_clusters(detections, radius_km=2.0, time_gap_hours=48)
    assert len(fires) == 1


# ── Metadata accuracy ─────────────────────────────────────────────────────────
def test_first_last_seen():
    detections = [
        det(61.000, 15.000, offset_hours=0),
        det(61.001, 15.001, offset_hours=5),
        det(61.002, 15.002, offset_hours=10),
    ]
    fires = build_fire_clusters(detections)
    f = fires[0]
    assert f["first_seen"] == dt(0)
    assert f["last_seen"] == dt(10)
    assert f["duration_hours"] == pytest.approx(10.0)


def test_max_frp():
    detections = [
        det(61.000, 15.000, frp=5.0),
        det(61.001, 15.001, frp=80.0),
        det(61.001, 15.002, frp=30.0),
    ]
    fires = build_fire_clusters(detections)
    assert fires[0]["max_frp"] == pytest.approx(80.0)


# ── Status ────────────────────────────────────────────────────────────────────
def test_active_status():
    now = dt(0)
    detections = [det(61.0, 15.0, offset_hours=-10)]  # 10h ago → active
    fires = build_fire_clusters(detections, active_threshold_hours=48, now=now)
    assert fires[0]["status"] == "active"


def test_inactive_status():
    now = dt(0)
    detections = [det(61.0, 15.0, offset_hours=-60)]  # 60h ago → inactive
    fires = build_fire_clusters(detections, active_threshold_hours=48, now=now)
    assert fires[0]["status"] == "inactive"


def test_empty_input():
    assert build_fire_clusters([]) == []
