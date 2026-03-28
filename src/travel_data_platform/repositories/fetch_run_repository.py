import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from travel_data_platform.database.models.fetch_run import FetchRun
from travel_data_platform.domain.flight import FlightQuery


class FetchRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_running(self, source: str, query: FlightQuery) -> FetchRun:
        now = datetime.now(UTC)

        row = FetchRun(
            id=uuid.uuid4(),
            source=source,
            status="RUNNING",
            origin=query.origin,
            destination=query.destination,
            departure_date=query.departure_date,
            return_date=query.return_date,
            adults=query.adults,
            query_payload=query.model_dump(),
            started_at=now,
            completed_at=None,
            duration_ms=None,
            raw_offer_count=0,
            normalized_offer_count=0,
            error_message=None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def mark_success(
        self,
        fetch_run: FetchRun,
        raw_offer_count: int,
        normalized_offer_count: int,
    ) -> FetchRun:
        completed_at = datetime.now(UTC)
        duration_ms = int((completed_at - fetch_run.started_at).total_seconds() * 1000)

        fetch_run.status = "SUCCESS"
        fetch_run.completed_at = completed_at
        fetch_run.duration_ms = duration_ms
        fetch_run.raw_offer_count = raw_offer_count
        fetch_run.normalized_offer_count = normalized_offer_count

        self.db.add(fetch_run)
        self.db.flush()
        return fetch_run

    def mark_failed(self, fetch_run: FetchRun, error_message: str) -> FetchRun:
        completed_at = datetime.now(UTC)
        duration_ms = int((completed_at - fetch_run.started_at).total_seconds() * 1000)

        fetch_run.status = "FAILED"
        fetch_run.completed_at = completed_at
        fetch_run.duration_ms = duration_ms
        fetch_run.error_message = error_message

        self.db.add(fetch_run)
        self.db.flush()
        return fetch_run