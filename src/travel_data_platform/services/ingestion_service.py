from sqlalchemy.orm import Session

from travel_data_platform.database.session import SessionLocal
from travel_data_platform.domain.ingestion import IngestionResult
from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.providers.google_flights.client import GoogleFlightsProvider
from travel_data_platform.providers.google_flights.debug.artifacts import write_debug_json
from travel_data_platform.repositories.fetch_run_repository import FetchRunRepository
from travel_data_platform.repositories.raw_flight_offer_repository import RawFlightOfferRepository
from travel_data_platform.repositories.normalized_flight_offer_repository import (
    NormalizedFlightOfferRepository,
)


class IngestionService:
    def __init__(self, provider: GoogleFlightsProvider) -> None:
        self.provider = provider or GoogleFlightsProvider()
        self.source = "google_flights"

    async def ingest_google_flights(self, query: FlightQuery) -> IngestionResult:
        db: Session = SessionLocal()

        try:
            fetch_run_repo = FetchRunRepository(db)
            raw_offer_repo = RawFlightOfferRepository(db)
            normalized_offer_repo = NormalizedFlightOfferRepository(db)

            fetch_run = fetch_run_repo.create_running(
                source=self.source,
                query=query,
            )
            db.commit()

            raw_offers = await self.provider.fetcher.fetch_raw(query)

            write_debug_json(f"{fetch_run.id}_raw_offers", raw_offers)

            raw_offer_repo.bulk_create(
                fetch_run_id=fetch_run.id,
                offers=raw_offers,
            )
            db.commit()

            offers = await self.provider.search(query)

            write_debug_json(
                f"{fetch_run.id}_normalized_offers",
                [offer.model_dump() for offer in offers],
            )

            normalized_offer_repo.bulk_create(
                fetch_run_id=fetch_run.id,
                source=self.source,
                query=query,
                offers=offers,
            )

            fetch_run_repo.mark_success(
                fetch_run=fetch_run,
                raw_offer_count=len(raw_offers),
                normalized_offer_count=len(offers),
            )
            db.commit()

            return IngestionResult(
                fetch_run_id=str(fetch_run.id),
                source=self.source,
                fetched_at=fetch_run.created_at.isoformat() if fetch_run.created_at else "",
                query=query,
                raw_offer_count=len(raw_offers),
                normalized_offer_count=len(offers),
                offers=offers,
            )

        except Exception as exc:
            db.rollback()

            try:
                fetch_run = locals().get("fetch_run")
                if fetch_run is not None:
                    fetch_run_repo = FetchRunRepository(db)
                    fetch_run_repo.mark_failed(fetch_run=fetch_run, error_message=str(exc))
                    db.commit()
            except Exception:
                db.rollback()

            raise

        finally:
            db.close()