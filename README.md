# 🔥 Brandkarta — Skogsbrandspårning med satellidata

Enkelsidig webbapp som visar aktiva och historiska skogs- och markbränder på en karta baserat på satellitdata från NASA FIRMS/VIIRS.

## ⚠️ Viktig information om datakällan

All branddata kommer från **satellit-värmesignaturer (hotspots)** via NASA FIRMS (VIIRS/SNPP).
Detta är **inte** officiella brandrapporter från räddningstjänst eller myndigheter.

- En "brand" i appen = ett kluster av värmesignaturer detekterade av satellit
- Kan inkludera industrivärme, bränning av jordbruksmark, solreflektion m.m.
- Status (aktiv/inaktiv) baseras uteslutande på om detektioner inkommit de senaste 48h
- Orsak till brand och officiell status anges inte

## Snabbstart

### Förutsättningar
- Python 3.12+
- En gratis NASA FIRMS MAP_KEY — registrera på https://firms.modaps.eosdis.nasa.gov/api/map_key/

### Lokal körning

```bash
cd Fire_Tracker
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Redigera .env — sätt FIRMS_MAP_KEY

uvicorn app.main:app --reload
```

Öppna http://localhost:8000

### Tester

```bash
pytest
```

## Driftsättning på Railway

1. Skapa ett nytt Railway-projekt och koppla detta repo
2. Lägg till miljövariabler (se `.env.example`):
   - `FIRMS_MAP_KEY` — din NASA FIRMS-nyckel
   - `DATABASE_URL` — Railway sätter denna automatiskt om du lägger till Postgres-plugin
3. Railway bygger automatiskt via `Dockerfile`

### Databas på Railway

Railway's filsystem är **efemärt** — SQLite-filen nollställs vid varje deploy.
För att bevara historik: lägg till **PostgreSQL**-pluginet i Railway.
Railway sätter då `DATABASE_URL` automatiskt med rätt connection string.

Appen stödjer både SQLite och PostgreSQL utan kodändringar.

## Arkitektur

```
[APScheduler (var 4h)] → [FIRMS API] → [Klustringslogik (DBSCAN)] → [SQLite/Postgres]
                                                                              ↓
                                                                     [FastAPI backend]
                                                                              ↓
                                                              [Leaflet-karta (SPA frontend)]
```

## Miljövariabler

| Variabel | Standard | Beskrivning |
|---|---|---|
| `FIRMS_MAP_KEY` | _(krävs)_ | NASA FIRMS API-nyckel |
| `FIRMS_SOURCE` | `VIIRS_SNPP_NRT` | Satellitdatakälla |
| `FIRMS_AREA` | `4,54,32,71` | Bounding box (Norden) |
| `FIRMS_DAY_RANGE` | `3` | Dagars data per hämtning |
| `FETCH_INTERVAL_HOURS` | `4` | Hämtningsintervall (timmar) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./fire_tracker.db` | Databas-URL |
| `CLUSTER_RADIUS_KM` | `2.0` | DBSCAN-radie för klustring |
| `CLUSTER_TIME_GAP_HOURS` | `48` | Tidsgap innan ny brand skapas |
| `ACTIVE_THRESHOLD_HOURS` | `48` | Timmar utan detektion → inaktiv |

## API-endpoints

| Endpoint | Beskrivning |
|---|---|
| `GET /fires?status=active` | Aktiva bränder (GeoJSON) |
| `GET /fires?status=inactive&from=2024-07-01&to=2024-07-31` | Historisk sökning |
| `GET /fires/{fire_id}` | Detaljer för en brand inkl. rådetektioner |
| `GET /health` | Hälsostatus |
| `GET /ingestion-log` | Loggar för datahämtning |
