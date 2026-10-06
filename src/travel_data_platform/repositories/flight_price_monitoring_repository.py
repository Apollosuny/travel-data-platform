import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from travel_data_platform.database.models.fetch_run import FetchRun
from travel_data_platform.database.models.flight_watch import FlightWatch
from travel_data_platform.database.models.normalized_flight_offer import (
    NormalizedFlightOffer,
)


class FlightPriceMonitoringRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_watch_by_id(self, flight_watch_id: uuid.UUID) -> FlightWatch | None:
        return self.db.get(FlightWatch, flight_watch_id)

    def get_cheapest_offer_for_fetch_run(
        self,
        fetch_run_id: uuid.UUID,
        watch: FlightWatch | None = None,
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
        if watch is not None:
            stmt = _apply_watch_offer_filters(stmt, watch)

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
        stmt = _apply_watch_offer_filters(stmt, watch)

        return self.db.execute(stmt).scalar_one_or_none()


def _apply_watch_offer_filters(stmt: Select[Any], watch: FlightWatch) -> Select[Any]:
    """Restrict offers to the watch's departure window and stop limit.

    Offers with an unknown departure time or stop count are excluded whenever the
    corresponding filter is set, so an unparsed offer can never trigger an alert.
    """
    if watch.departure_time_from is not None:
        stmt = stmt.where(NormalizedFlightOffer.departure_time_local >= watch.departure_time_from)
    if watch.departure_time_to is not None:
        stmt = stmt.where(NormalizedFlightOffer.departure_time_local <= watch.departure_time_to)
    if watch.max_stops is not None:
        stmt = stmt.where(NormalizedFlightOffer.stops <= watch.max_stops)
    return stmt
