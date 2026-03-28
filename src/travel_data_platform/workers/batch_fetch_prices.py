import asyncio
import logging
from datetime import UTC, datetime

from travel_data_platform.config import settings
from travel_data_platform.database.session import SessionLocal
from travel_data_platform.logging import setup_logging
from travel_data_platform.repositories.flight_watch_repository import FlightWatchRepository
from travel_data_platform.services.batch_ingestion_service import BatchIngestionService
from travel_data_platform.services.watch_query_service import WatchQueryService


async def main() -> None:
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    db = SessionLocal()
    try:
        watch_repo = FlightWatchRepository(db)
        watches = watch_repo.list_due_active_watches()
    finally:
        db.close()

    if not watches:
        logger.info("batch_completed total_queries=0 success=0 failed=0")
        return

    query_service = WatchQueryService()
    queries = [query_service.to_query(watch) for watch in watches]

    service = BatchIngestionService(concurrency=2)
    results = await service.ingest_queries(queries)

    success_count = 0
    failed_count = 0

    db = SessionLocal()
    try:
        watch_repo = FlightWatchRepository(db)

        for watch, query, result in zip(watches, queries, results):
            if isinstance(result, Exception):
                failed_count += 1
                logger.exception(
                    "watch_id=%s route=%s-%s failed",
                    watch.id,
                    query.origin,
                    query.destination,
                    exc_info=result,
                )
                continue

            success_count += 1
            logger.info(
                "watch_id=%s fetch_run_id=%s route=%s-%s raw=%s normalized=%s",
                watch.id,
                result.fetch_run_id,
                query.origin,
                query.destination,
                result.raw_offer_count,
                result.normalized_offer_count,
            )

            watch_repo.update_last_checked_at(watch.id, datetime.now(UTC))

        db.commit()
    finally:
        db.close()

    logger.info(
        "batch_completed total_queries=%s success=%s failed=%s",
        len(watches),
        success_count,
        failed_count,
    )


if __name__ == "__main__":
    asyncio.run(main())