import asyncio
import logging
from datetime import UTC, datetime

from travel_data_platform.config import settings
from travel_data_platform.database.session import SessionLocal
from travel_data_platform.logging import setup_logging
from travel_data_platform.repositories.flight_watch_repository import (
    FlightWatchRepository,
)
from travel_data_platform.services.batch_ingestion_service import BatchIngestionService


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
        logger.info("batch_completed total_watches=0 success=0 failed=0")
        return

    service = BatchIngestionService(concurrency=1)
    summary = await service.ingest_watches(watches)

    successful_watch_ids = {
        result.watch_id for result in summary.results if result.success
    }

    if successful_watch_ids:
        db = SessionLocal()
        try:
            watch_repo = FlightWatchRepository(db)
            now = datetime.now(UTC)
            for watch in watches:
                if str(watch.id) in successful_watch_ids:
                    watch_repo.update_last_checked_at(watch.id, now)
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    asyncio.run(main())
