import uuid
from sqlalchemy.orm import Session

from travel_data_platform.database.models.raw_flight_offer import RawFlightOffer


class RawFlightOfferRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def bulk_create(self, fetch_run_id: uuid.UUID, offers: list[dict]) -> list[RawFlightOffer]:
        rows: list[RawFlightOffer] = []

        for index, offer in enumerate(offers, start=1):
            row = RawFlightOffer(
                id=uuid.uuid4(),
                fetch_run_id=fetch_run_id,
                offer_rank=index,
                price=offer["price"],
                currency=offer["currency"],
                airline=offer.get("airline"),
                stops=offer.get("stops"),
                duration_text=offer.get("duration_text"),
                departure_time_text=offer.get("departure_time_text"),
                arrival_time_text=offer.get("arrival_time_text"),
                card_aria_label=offer.get("card_aria_label"),
                source_url=offer.get("source_url"),
                raw_payload=offer,
            )
            rows.append(row)

        self.db.add_all(rows)
        self.db.flush()
        return rows