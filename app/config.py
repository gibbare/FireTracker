from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    firms_map_key: str = ""
    firms_source: str = "VIIRS_SNPP_NRT"
    firms_area: str = "4,54,32,71"   # Norden bounding box
    firms_day_range: int = 3   # VIIRS_SNPP_NRT accepts max 5
    fetch_interval_hours: int = 4
    database_url: str = "sqlite+aiosqlite:///./fire_tracker.db"
    # How many hours without detection before a fire is considered inactive
    active_threshold_hours: int = 48
    # DBSCAN clustering radius in km
    cluster_radius_km: float = 2.0
    # Max gap in hours before treating as a new fire at the same location
    cluster_time_gap_hours: int = 48

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
