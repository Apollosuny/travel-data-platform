import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Integer, BigInteger, SmallInteger, Text, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from travel_data_platform.database.base import Base


class NormalizedFlightOffer(Base):
    __tablename__ = "normalized_flight_offers"
    __table_args__ = {"schema": "ingestion"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    fetch_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion.fetch_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    route_key: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    offer_rank: Mapped[int] = mapped_column(Integer, nullable=False)

    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    airline: Mapped[str | None] = mapped_column(Text, nullable=True)
    stops: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    departure_time_local: Mapped[time | None] = mapped_column(Time, nullable=True)
    arrival_time_local: Mapped[time | None] = mapped_column(Time, nullable=True)

    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )