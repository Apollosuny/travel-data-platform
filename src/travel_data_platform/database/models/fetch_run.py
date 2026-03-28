import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from travel_data_platform.database.base import Base

class FetchRun(Base):
  __tablename__ = "fetch_runs"
  __table_args__ = { "schema": "ingestion" }

  id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

  source: Mapped[str] = mapped_column(Text, nullable=False)
  status: Mapped[str] = mapped_column(Text, nullable=False)
  
  origin: Mapped[str] = mapped_column(Text, nullable=False)
  destination: Mapped[str] = mapped_column(Text, nullable=False)
  departure_date: Mapped[date] = mapped_column(Date, nullable=False)
  return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
  adults: Mapped[int] = mapped_column(SmallInteger, nullable=False)

  query_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

  started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
  completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

  raw_offer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
  normalized_offer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

  error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True),
      nullable=False,
      server_default=func.now(),
  )
