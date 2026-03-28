import uuid
from datetime import time
from sqlalchemy.orm import Session

from travel_data_platform.database.models.normalized_flight_offer import NormalizedFlightOffer
from travel_data_platform.domain.flight import FlightOffer, FlightQuery


class NormalizedFlightOfferRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def bulk_create(
        self,
        fetch_run_id: uuid.UUID,
        source: str,
        query: FlightQuery,
        offers: list[FlightOffer],
    ) -> list[NormalizedFlightOffer]:
        rows: list[NormalizedFlightOffer] = []

        for index, offer in enumerate(offers, start=1):
            row = NormalizedFlightOffer(
                id=uuid.uuid4(),
                fetch_run_id=fetch_run_id,
                route_key=f"{query.origin}-{query.destination}",
                source=source,
                offer_rank=index,
                price=offer.price,
                currency=offer.currency,
                airline=offer.airline,
                stops=offer.stops,
                duration_minutes=None,
                departure_time_local=None,
                arrival_time_local=None,
                departure_date=query.departure_date,
                origin=query.origin,
                destination=query.destination,
            )
            rows.append(row)

        self.db.add_all(rows)
        self.db.flush()
        return rows