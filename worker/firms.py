"""FIRMS API client — fetches satellite fire detections."""

import csv
import io
from datetime import datetime, timezone
from typing import Optional
import httpx

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

ERROR_EXPLANATIONS: dict[str, str] = {
    "400": "Felaktig förfrågan — kontrollera att FIRMS_AREA och FIRMS_SOURCE är korrekta.",
    "401": "Ogiltig API-nyckel (MAP_KEY) — nyckel saknas, har gått ut, eller är felaktig. Kontrollera miljövariabeln FIRMS_MAP_KEY.",
    "403": "Åtkomst nekad — MAP_KEY saknar behörighet för den begärda källan.",
    "429": "Rate limit nådd — för många anrop inom 10 minuter. Vänta och försök igen.",
    "500": "FIRMS-servern returnerade ett internt serverfel. Försök igen senare.",
    "503": "FIRMS-tjänsten är tillfälligt otillgänglig. Försök igen senare.",
    "timeout": "Anropet till FIRMS tog för lång tid (timeout). FIRMS-tjänsten svarar inte just nu.",
    "connection": "Kunde inte ansluta till FIRMS — kontrollera nätverksanslutningen.",
    "parse": "Svaret från FIRMS kunde inte tolkas som giltig CSV-data.",
    "empty": "FIRMS returnerade inga detektioner för det angivna området och tidsintervallet.",
}


def _explain(code: str) -> str:
    return ERROR_EXPLANATIONS.get(code, f"Okänt fel ({code}).")


class FirmsError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        self.human = _explain(code)
        super().__init__(message)


def _parse_csv(text: str) -> list[dict]:
    """Parse FIRMS CSV response into list of detection dicts."""
    if not text or not text.strip():
        return []

    reader = csv.DictReader(io.StringIO(text.strip()))
    rows = []
    try:
        for row in reader:
            lat = row.get("latitude") or row.get("lat")
            lon = row.get("longitude") or row.get("lon") or row.get("long")
            acq_date = row.get("acq_date", "")
            acq_time = row.get("acq_time", "0000")
            confidence = row.get("confidence", "")
            frp_raw = row.get("frp", "0") or "0"
            source = row.get("instrument", "VIIRS")

            if not lat or not lon or not acq_date:
                continue

            try:
                acq_time_str = str(acq_time).zfill(4)
                dt = datetime.strptime(
                    f"{acq_date} {acq_time_str}", "%Y-%m-%d %H%M"
                ).replace(tzinfo=timezone.utc)
                rows.append(
                    {
                        "latitude": float(lat),
                        "longitude": float(lon),
                        "acq_datetime": dt,
                        "confidence": str(confidence),
                        "frp": float(frp_raw) if frp_raw else 0.0,
                        "source": source,
                    }
                )
            except (ValueError, KeyError):
                continue
    except csv.Error as exc:
        raise FirmsError("parse", str(exc))

    return rows


def fetch_detections(
    map_key: str,
    source: str,
    area: str,
    day_range: int,
    timeout: float = 30.0,
    client: Optional[httpx.Client] = None,
) -> list[dict]:
    """Fetch fire detections from FIRMS API (synchronous)."""
    url = f"{FIRMS_BASE}/{map_key}/{source}/{area}/{day_range}"

    _client = client or httpx.Client(timeout=timeout)
    try:
        response = _client.get(url)
    except httpx.TimeoutException as exc:
        raise FirmsError("timeout", str(exc))
    except httpx.ConnectError as exc:
        raise FirmsError("connection", str(exc))
    finally:
        if client is None:
            _client.close()

    if response.status_code != 200:
        raise FirmsError(str(response.status_code), response.text[:500])

    text = response.text
    # FIRMS sometimes returns HTML error pages with status 200
    if text.strip().startswith("<"):
        raise FirmsError("parse", "Unexpected HTML response — possible API key issue.")

    return _parse_csv(text)
