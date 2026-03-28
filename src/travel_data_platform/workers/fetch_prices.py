import asyncio
import logging

from travel_data_platform.config import settings
from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.domain.ingestion import FetchRunEnvelope
from travel_data_platform.logging import setup_logging
from travel_data_platform.providers.google_flights.fetchers.browser_fetcher import GoogleFlightsBrowserFetcher
from travel_data_platform.providers.google_flights.debug.artifacts import write_debug_json
from travel_data_platform.services.flight_price_service import FlightPriceService


async def main():
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    query = FlightQuery(
        origin="HAN",
        destination="BKK",
        departure_date="2026-04-20",
        return_date="2026-04-25",
        adults=1,
    )

    fetcher = GoogleFlightsBrowserFetcher()
    raw_offers = await fetcher.fetch_raw(query)

    raw_run = FetchRunEnvelope.create(
        source="google_flights",
        query=query,
        offers=raw_offers
    )
    write_debug_json("raw_fetch_run", raw_run.model_dump())

    service = FlightPriceService()
    offers = await service.fetch_prices(query)
    
    logger.info("fetched_offers", extra={"count": len(offers)})
    for offer in offers:
        print(offer.model_dump())


if __name__ == "__main__":
    asyncio.run(main())