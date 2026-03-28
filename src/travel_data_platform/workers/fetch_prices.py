import asyncio
import logging

from travel_data_platform.config import settings
from travel_data_platform.logging import setup_logging
from travel_data_platform.providers.base import FlightQuery
from travel_data_platform.pipelines.flight_prices.service import FlightPriceService


async def main():
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    service = FlightPriceService()

    query = FlightQuery(
        origin="HAN",
        destination="BKK",
        departure_date="2026-04-20",
        return_date="2026-04-25",
        adults=1,
    )

    offers = await service.fetch_prices(query)
    logger.info("fetched_offers", extra={"count": len(offers)})

    for offer in offers:
        print(offer.model_dump())


if __name__ == "__main__":
    asyncio.run(main())