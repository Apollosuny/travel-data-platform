import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from travel_data_platform.database.models.fetch_run import FetchRun
from travel_data_platform.database.models.normalized_flight_offer import (
    NormalizedFlightOffer,
)
from travel_data_platform.database.models.flight_watch import FlightWatch


class FlightPriceMonitoringRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_watch_by_id(self, flight_watch_id: uuid.UUID) -> FlightWatch | None:
        return self.db.get(FlightWatch, flight_watch_id)

    def get_cheapest_offer_for_fetch_run(
        self,
        fetch_run_id: uuid.UUID,
    ) -> NormalizedFlightOffer | None:
        stmt: Select[tuple[NormalizedFlightOffer]] = (
            select(NormalizedFlightOffer)
            .where(NormalizedFlightOffer.fetch_run_id == fetch_run_id)
            .order_by(
                NormalizedFlightOffer.price.asc(),
                NormalizedFlightOffer.offer_rank.asc(),
            )
            .limit(1)
        )

        return self.db.execute(stmt).scalars().first()

    def get_min_price_7d_for_watch(
        self,
        watch: FlightWatch,
        now: datetime | None = None,
    ) -> int | None:
        now = now or datetime.now(UTC)
        start_time = now - timedelta(days=7)

        stmt = (
            select(func.min(NormalizedFlightOffer.price))
            .join(
                FetchRun,
                FetchRun.id == NormalizedFlightOffer.fetch_run_id,
            )
            .where(FetchRun.status == "SUCCESS")
            .where(FetchRun.origin == watch.origin)
            .where(FetchRun.destination == watch.destination)
            .where(FetchRun.departure_date == watch.departure_date)
            .where(FetchRun.return_date == watch.return_date)
            .where(FetchRun.adults == watch.adults)
            .where(FetchRun.created_at >= start_time)
        )

        return self.db.execute(stmt).scalar_one_or_none()
