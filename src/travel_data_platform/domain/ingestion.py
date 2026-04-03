from pydantic import BaseModel
from datetime import UTC, datetime
from uuid import uuid4

from travel_data_platform.domain.flight import FlightOffer, FlightQuery

class FetchRunEnvelope(BaseModel):
  fetch_run_id: str
  source: str
  fetched_at: str
  query: FlightQuery
  offers: list[dict]

  @classmethod
  def create(cls, source: str, query: FlightQuery, offers: list[dict]) -> "FetchRunEnvelope":
    return cls(
            fetch_run_id=str(uuid4()),
            source=source,
            fetched_at=datetime.now(UTC).isoformat(),
            query=query,
            offers=offers,
        )

class IngestionResult(BaseModel):
  fetch_run_id: str
  source: str
  fetched_at: str
  query: FlightQuery
  raw_offer_count: int
  normalized_offer_count: int
  offers: list[FlightOffer]
  warnings: list[str] = []

class BatchWatchResult(BaseModel):
    watch_id: str
    route: str
    success: bool
    fetch_run_id: str | None = None
    raw_offer_count: int = 0
    normalized_offer_count: int = 0
    error_message: str | None = None
    warnings: list[str] = []


class BatchJobSummary(BaseModel):
    total_watches: int
    success_count: int
    failed_count: int
    warning_count: int
    duration_ms: int
    results: list[BatchWatchResult]