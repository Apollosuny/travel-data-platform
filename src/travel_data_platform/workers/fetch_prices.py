import asyncio
import logging
import sys
from datetime import UTC, datetime

from travel_data_platform.config import settings
from travel_data_platform.database.session import SessionLocal
from travel_data_platform.logging import setup_logging
from travel_data_platform.repositories.flight_watch_repository import FlightWatchRepository
from travel_data_platform.services.batch_ingestion_service import BatchIngestionService


async def main() -> int:
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    db = SessionLocal()
    try:
        watch_repo = FlightWatchRepository(db)
        watches = watch_repo.list_due_active_watches()
    finally:
        db.close()

    if not watches:
        logger.info("batch_completed total_watches=0 success=0 failed=0 warnings=0 duration_ms=0")
        return 0

    service = BatchIngestionService(concurrency=2)
    summary = await service.ingest_watches(watches)

    db = SessionLocal()
    try:
        watch_repo = FlightWatchRepository(db)

        for watch, result in zip(watches, summary.results):
            if result.success:
                watch_repo.update_last_checked_at(watch.id, datetime.now(UTC))

        db.commit()
    finally:
        db.close()

    for result in summary.results:
        if result.success:
            logger.info(
                "watch_result watch_id=%s route=%s success=true fetch_run_id=%s raw=%s normalized=%s warnings=%s",
                result.watch_id,
                result.route,
                result.fetch_run_id,
                result.raw_offer_count,
                result.normalized_offer_count,
                len(result.warnings),
            )
        else:
            logger.error(
                "watch_result watch_id=%s route=%s success=false error=%s",
                result.watch_id,
                result.route,
                result.error_message,
            )

    return 0 if summary.failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))