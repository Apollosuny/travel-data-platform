from sqlalchemy.orm import Session

from travel_data_platform.database.session import SessionLocal
from travel_data_platform.domain.ingestion import IngestionResult
from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.providers.google_flights.client import GoogleFlightsProvider
from travel_data_platform.providers.google_flights.debug.artifacts import (
    write_debug_json,
)
from travel_data_platform.repositories.fetch_run_repository import FetchRunRepository
from travel_data_platform.repositories.raw_flight_offer_repository import (
    RawFlightOfferRepository,
)
from travel_data_platform.repositories.normalized_flight_offer_repository import (
    NormalizedFlightOfferRepository,
)
from travel_data_platform.repositories.flight_alert_event_repository import (
    FlightAlertEventRepository,
)
from travel_data_platform.repositories.flight_price_monitoring_repository import (
    FlightPriceMonitoringRepository,
)
from travel_data_platform.repositories.flight_watch_repository import (
    FlightWatchRepository,
)
from travel_data_platform.services.alert_rule_evaluator import AlertRuleEvaluator


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
            warnings = self._build_warnings(
                raw_offers=raw_offers,
                normalized_count=len(offers),
            )

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

            alert_count = self._create_alert_events(
                db=db, fetch_run_id=fetch_run.id, query=query
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
                fetched_at=(
                    fetch_run.created_at.isoformat() if fetch_run.created_at else ""
                ),
                query=query,
                raw_offer_count=len(raw_offers),
                normalized_offer_count=len(offers),
                offers=offers,
                warnings=warnings,
                alert_count=alert_count,
            )

        except Exception as exc:
            db.rollback()

            try:
                fetch_run = locals().get("fetch_run")
                if fetch_run is not None:
                    fetch_run_repo = FetchRunRepository(db)
                    fetch_run_repo.mark_failed(
                        fetch_run=fetch_run, error_message=str(exc)
                    )
                    db.commit()
            except Exception:
                db.rollback()

            raise

        finally:
            db.close()

    def _build_warnings(
        self,
        raw_offers: list[dict],
        normalized_count: int,
    ) -> list[str]:
        warnings: list[str] = []

        if len(raw_offers) == 0:
            warnings.append("raw_offer_count_is_zero")

        if normalized_count == 0:
            warnings.append("normalized_offer_count_is_zero")

        if len(raw_offers) > 0 and normalized_count == 0:
            warnings.append("raw_exists_but_normalized_empty")

        return warnings

    def _find_matching_watch(self, db: Session, query: FlightQuery):
        watch_repo = FlightWatchRepository(db)
        watches = watch_repo.list_due_active_watches()

        for watch in watches:
            if (
                watch.origin == query.origin
                and watch.destination == query.destination
                and watch.departure_date == query.departure_date
                and watch.return_date == query.return_date
                and watch.adults == query.adults
            ):
                return watch

        return None

    def _create_alert_events(
        self,
        db: Session,
        fetch_run_id,
        query: FlightQuery,
    ) -> int:
        watch = self._find_matching_watch(db, query)
        if watch is None:
            return 0

        monitoring_repo = FlightPriceMonitoringRepository(db)
        alert_repo = FlightAlertEventRepository(db)
        evaluator = AlertRuleEvaluator()

        cheapest_offer = monitoring_repo.get_cheapest_offer_for_fetch_run(fetch_run_id)
        if cheapest_offer is None:
            return 0

        min_price_7d = monitoring_repo.get_min_price_7d_for_watch(watch)

        candidates = evaluator.evaluate(
            current_price=cheapest_offer.price,
            currency=cheapest_offer.currency,
            target_price=watch.target_price,
            min_price_7d=min_price_7d,
        )

        created_count = 0
        for candidate in candidates:
            alert_repo.create(
                flight_watch_id=watch.id,
                fetch_run_id=fetch_run_id,
                alert_type=candidate.alert_type,
                current_price=candidate.current_price,
                currency=candidate.currency,
                baseline_price=candidate.baseline_price,
                target_price=candidate.target_price,
                message=candidate.message,
            )
            created_count += 1

        db.flush()
        return created_count
