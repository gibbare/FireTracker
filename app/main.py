import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import init_db, AsyncSessionLocal
from app.routers import fires, health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _scheduled_ingestion():
    from worker.ingestion import run_ingestion
    async with AsyncSessionLocal() as db:
        await run_ingestion(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialised")

    # Run once on startup, then on interval
    asyncio.create_task(_scheduled_ingestion())

    scheduler.add_job(
        _scheduled_ingestion,
        trigger=IntervalTrigger(hours=settings.fetch_interval_hours),
        id="firms_ingestion",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — ingestion every %d hours", settings.fetch_interval_hours
    )

    yield

    scheduler.shutdown()


app = FastAPI(title="Fire Tracker", lifespan=lifespan)

app.include_router(fires.router)
app.include_router(health.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def serve_spa():
    return FileResponse("app/static/index.html")
