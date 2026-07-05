"""Cluster raw FIRMS detections into fire events using DBSCAN + time gap splitting."""

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import numpy as np
from sklearn.cluster import DBSCAN

# Earth radius in km
_EARTH_R = 6371.0


def _haversine_rad(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in km between two points (degrees)."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_R * math.asin(math.sqrt(a))


def _spatial_cluster(
    detections: list[dict], radius_km: float
) -> list[list[dict]]:
    """Group detections by spatial proximity using DBSCAN."""
    if not detections:
        return []

    coords = np.array([[d["latitude"], d["longitude"]] for d in detections])
    coords_rad = np.radians(coords)
    eps = radius_km / _EARTH_R  # radians

    labels = DBSCAN(
        eps=eps, min_samples=1, algorithm="ball_tree", metric="haversine"
    ).fit_predict(coords_rad)

    groups: dict[int, list[dict]] = {}
    for i, label in enumerate(labels):
        groups.setdefault(label, []).append(detections[i])
    return list(groups.values())


def _split_by_time_gap(
    cluster: list[dict], gap_hours: int
) -> list[list[dict]]:
    """Split a spatial cluster into sub-clusters if there's a time gap > gap_hours."""
    sorted_pts = sorted(cluster, key=lambda d: d["acq_datetime"])
    gap = timedelta(hours=gap_hours)
    sub_clusters: list[list[dict]] = [[sorted_pts[0]]]
    for pt in sorted_pts[1:]:
        if pt["acq_datetime"] - sub_clusters[-1][-1]["acq_datetime"] > gap:
            sub_clusters.append([pt])
        else:
            sub_clusters[-1].append(pt)
    return sub_clusters


def build_fire_clusters(
    detections: list[dict],
    radius_km: float = 2.0,
    time_gap_hours: int = 48,
    active_threshold_hours: int = 48,
    now: Optional[datetime] = None,
) -> list[dict]:
    """
    Returns a list of fire dicts ready to upsert.
    Each fire has: fire_id, latitude, longitude, first_seen, last_seen,
    duration_hours, detections, max_frp, status, min_lat, max_lat, min_lon, max_lon,
    and a 'points' list of the raw detection dicts that belong to it.
    """
    if not detections:
        return []

    if now is None:
        now = datetime.now(timezone.utc)
    active_cutoff = now - timedelta(hours=active_threshold_hours)

    spatial_groups = _spatial_cluster(detections, radius_km)
    fires: list[dict] = []

    for group in spatial_groups:
        for sub in _split_by_time_gap(group, time_gap_hours):
            lats = [d["latitude"] for d in sub]
            lons = [d["longitude"] for d in sub]
            frps = [d["frp"] for d in sub if d.get("frp")]
            times = [d["acq_datetime"] for d in sub]

            first_seen = min(times)
            last_seen = max(times)
            duration = (last_seen - first_seen).total_seconds() / 3600

            fires.append(
                {
                    "fire_id": str(uuid.uuid4()),
                    "latitude": sum(lats) / len(lats),
                    "longitude": sum(lons) / len(lons),
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                    "duration_hours": round(duration, 2),
                    "detections": len(sub),
                    "max_frp": max(frps) if frps else 0.0,
                    "status": "active" if last_seen >= active_cutoff else "inactive",
                    "min_lat": min(lats),
                    "max_lat": max(lats),
                    "min_lon": min(lons),
                    "max_lon": max(lons),
                    "points": sub,
                }
            )

    return fires
