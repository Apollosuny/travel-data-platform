import asyncio
import logging

from travel_data_platform.config import settings
from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.logging import setup_logging
from travel_data_platform.services.ingestion_service import IngestionService


async def main() -> None:
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    queries = [
        FlightQuery(
            origin="HAN",
            destination="BKK",
            departure_date="2026-04-20",
            return_date="2026-04-25",
            adults=1,
        ),
        FlightQuery(
            origin="SGN",
            destination="BKK",
            departure_date="2026-04-20",
            return_date="2026-04-25",
            adults=1,
        ),
    ]

    service = IngestionService()
    results = []

    for query in queries:
        result = await service.ingest_google_flights(query)
        results.append(result)

        logger.info(
            "fetch_run_id=%s route=%s-%s raw=%s normalized=%s",
            result.fetch_run_id,
            query.origin,
            query.destination,
            result.raw_offer_count,
            result.normalized_offer_count,
        )

    logger.info("batch_completed total_queries=%s", len(results))


if __name__ == "__main__":
    asyncio.run(main())