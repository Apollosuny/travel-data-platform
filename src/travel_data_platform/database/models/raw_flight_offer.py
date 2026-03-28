import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, BigInteger, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from travel_data_platform.database.base import Base


class RawFlightOffer(Base):
    __tablename__ = "raw_flight_offers"
    __table_args__ = {"schema": "ingestion"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    fetch_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion.fetch_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    offer_rank: Mapped[int] = mapped_column(Integer, nullable=False)

    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    airline: Mapped[str | None] = mapped_column(Text, nullable=True)
    stops: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    duration_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    departure_time_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    arrival_time_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    card_aria_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )