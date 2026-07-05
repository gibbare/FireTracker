import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Fire(Base):
    __tablename__ = "fires"

    fire_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_frp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # Representative bounding box for the cluster
    min_lat: Mapped[float] = mapped_column(Float, nullable=True)
    max_lat: Mapped[float] = mapped_column(Float, nullable=True)
    min_lon: Mapped[float] = mapped_column(Float, nullable=True)
    max_lon: Mapped[float] = mapped_column(Float, nullable=True)

    raw_detections: Mapped[list["RawDetection"]] = relationship(
        back_populates="fire", cascade="all, delete-orphan"
    )


class RawDetection(Base):
    __tablename__ = "raw_detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fire_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fires.fire_id"), nullable=False
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    acq_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=True)
    frp: Mapped[float] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=True)

    fire: Mapped["Fire"] = relationship(back_populates="raw_detections")


class IngestionLog(Base):
    __tablename__ = "ingestion_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    human_explanation: Mapped[str] = mapped_column(Text, nullable=True)
    detections_fetched: Mapped[int] = mapped_column(Integer, nullable=True)
    fires_updated: Mapped[int] = mapped_column(Integer, nullable=True)
