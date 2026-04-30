import asyncio
import logging
import time

from travel_data_platform.database.models.flight_watch import FlightWatch
from travel_data_platform.domain.ingestion import BatchJobSummary, BatchWatchResult
from travel_data_platform.providers.google_flights.client import GoogleFlightsProvider
from travel_data_platform.providers.google_flights.fetchers.playwright_fetcher import (
    GoogleFlightsPlaywrightFetcher,
)
from travel_data_platform.services.ingestion_service import IngestionService
from travel_data_platform.services.watch_query_service import WatchQueryService


class BatchIngestionService:
    def __init__(self, concurrency: int = 2) -> None:
        self.concurrency = concurrency
        self.logger = logging.getLogger(__name__)
        self.query_service = WatchQueryService()

    async def ingest_watches(self, watches: list[FlightWatch]) -> BatchJobSummary:
        started_at = time.perf_counter()

        if not watches:
            return BatchJobSummary(
                total_watches=0,
                success_count=0,
                failed_count=0,
                warning_count=0,
                duration_ms=0,
                results=[],
            )

        self.logger.info(
            "batch_started total_watches=%s concurrency=%s",
            len(watches),
            self.concurrency,
        )

        provider = self._build_provider()
        semaphore = asyncio.Semaphore(self.concurrency)

        async def run_one(watch: FlightWatch) -> BatchWatchResult:
            query = self.query_service.to_query(watch)
            route = f"{query.origin}-{query.destination}"

            async with semaphore:
                self.logger.info("watch_started watch_id=%s route=%s", watch.id, route)

                try:
                    service = IngestionService(provider=provider)
                    result = await service.ingest_google_flights(query)

                    self.logger.info(
                        "watch_finished watch_id=%s route=%s fetch_run_id=%s "
                        "raw=%s normalized=%s warnings=%s alerts=%s",
                        watch.id,
                        route,
                        result.fetch_run_id,
                        result.raw_offer_count,
                        result.normalized_offer_count,
                        len(result.warnings),
                        result.alert_count,
                    )

                    return BatchWatchResult(
                        watch_id=str(watch.id),
                        route=route,
                        success=True,
                        fetch_run_id=result.fetch_run_id,
                        raw_offer_count=result.raw_offer_count,
                        normalized_offer_count=result.normalized_offer_count,
                        warnings=result.warnings,
                    )

                except Exception as exc:
                    self.logger.exception(
                        "watch_failed watch_id=%s route=%s",
                        watch.id,
                        route,
                    )
                    return BatchWatchResult(
                        watch_id=str(watch.id),
                        route=route,
                        success=False,
                        error_message=str(exc),
                    )

        tasks = [run_one(watch) for watch in watches]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for item in results if item.success)
        failed_count = sum(1 for item in results if not item.success)
        warning_count = sum(len(item.warnings) for item in results)
        duration_ms = int((time.perf_counter() - started_at) * 1000)

        summary = BatchJobSummary(
            total_watches=len(watches),
            success_count=success_count,
            failed_count=failed_count,
            warning_count=warning_count,
            duration_ms=duration_ms,
            results=results,
        )

        self.logger.info(
            "batch_completed total_watches=%s success=%s failed=%s warnings=%s duration_ms=%s",
            summary.total_watches,
            summary.success_count,
            summary.failed_count,
            summary.warning_count,
            summary.duration_ms,
        )

        return summary

    def _build_provider(self) -> GoogleFlightsProvider:
        return GoogleFlightsProvider(fetcher=GoogleFlightsPlaywrightFetcher())
