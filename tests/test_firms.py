"""Tests for FIRMS API client — no real network calls."""

import pytest
import httpx
import respx

from worker.firms import fetch_detections, FirmsError, _parse_csv

SAMPLE_CSV = """\
latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight
61.123,15.456,310.5,0.39,0.36,2024-07-15,0845,N,VIIRS,nominal,2.0NRT,287.3,12.5,D
62.000,16.000,320.0,0.39,0.36,2024-07-15,0845,N,VIIRS,high,2.0NRT,290.0,45.2,D
"""

EMPTY_CSV = "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n"


def test_parse_csv_valid():
    rows = _parse_csv(SAMPLE_CSV)
    assert len(rows) == 2
    assert rows[0]["latitude"] == pytest.approx(61.123)
    assert rows[0]["longitude"] == pytest.approx(15.456)
    assert rows[0]["frp"] == pytest.approx(12.5)
    assert rows[1]["frp"] == pytest.approx(45.2)


def test_parse_csv_empty_body():
    rows = _parse_csv("")
    assert rows == []


def test_parse_csv_header_only():
    rows = _parse_csv(EMPTY_CSV)
    assert rows == []


def test_parse_csv_missing_coords():
    csv_text = "latitude,longitude,acq_date,acq_time,frp\n,15.0,2024-07-15,0845,10.0\n"
    rows = _parse_csv(csv_text)
    assert rows == []


@respx.mock
def test_fetch_detections_success():
    respx.get("https://firms.modaps.eosdis.nasa.gov/api/area/csv/TESTKEY/VIIRS_SNPP_NRT/10,55,25,69/3").mock(
        return_value=httpx.Response(200, text=SAMPLE_CSV)
    )
    rows = fetch_detections("TESTKEY", "VIIRS_SNPP_NRT", "10,55,25,69", 3)
    assert len(rows) == 2


@respx.mock
def test_fetch_detections_401():
    respx.get("https://firms.modaps.eosdis.nasa.gov/api/area/csv/BADKEY/VIIRS_SNPP_NRT/10,55,25,69/3").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    with pytest.raises(FirmsError) as exc_info:
        fetch_detections("BADKEY", "VIIRS_SNPP_NRT", "10,55,25,69", 3)
    assert exc_info.value.code == "401"
    assert "MAP_KEY" in exc_info.value.human


@respx.mock
def test_fetch_detections_429():
    respx.get("https://firms.modaps.eosdis.nasa.gov/api/area/csv/K/VIIRS_SNPP_NRT/10,55,25,69/3").mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )
    with pytest.raises(FirmsError) as exc_info:
        fetch_detections("K", "VIIRS_SNPP_NRT", "10,55,25,69", 3)
    assert exc_info.value.code == "429"
    assert "Rate limit" in exc_info.value.human


@respx.mock
def test_fetch_detections_html_response():
    """FIRMS sometimes returns HTML even with 200 status."""
    respx.get("https://firms.modaps.eosdis.nasa.gov/api/area/csv/K/VIIRS_SNPP_NRT/10,55,25,69/3").mock(
        return_value=httpx.Response(200, text="<html><body>Error</body></html>")
    )
    with pytest.raises(FirmsError) as exc_info:
        fetch_detections("K", "VIIRS_SNPP_NRT", "10,55,25,69", 3)
    assert exc_info.value.code == "parse"


@respx.mock
def test_fetch_detections_timeout():
    respx.get("https://firms.modaps.eosdis.nasa.gov/api/area/csv/K/VIIRS_SNPP_NRT/10,55,25,69/3").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    with pytest.raises(FirmsError) as exc_info:
        fetch_detections("K", "VIIRS_SNPP_NRT", "10,55,25,69", 3)
    assert exc_info.value.code == "timeout"
    assert "Timeout" in exc_info.value.human
