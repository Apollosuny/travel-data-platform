import asyncio
import logging

from playwright.async_api import Browser

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.providers.google_flights.client import GoogleFlightsProvider
from travel_data_platform.providers.google_flights.fetchers.browser_fetcher import (
    GoogleFlightsBrowserFetcher,
)
from travel_data_platform.providers.google_flights.runtime.browser_runtime import (
    google_flights_browser,
)
from travel_data_platform.services.ingestion_service import IngestionService


class BatchIngestionService:
    def __init__(self, concurrency: int = 2) -> None:
        self.concurrency = concurrency
        self.logger = logging.getLogger(__name__)

    async def ingest_queries(self, queries: list[FlightQuery]):
        async with google_flights_browser() as browser:
            semaphore = asyncio.Semaphore(self.concurrency)

            async def run_one(query: FlightQuery):
                async with semaphore:
                    provider = self._build_provider(browser)
                    service = IngestionService(provider=provider)
                    return await service.ingest_google_flights(query)

            tasks = [run_one(query) for query in queries]
            return await asyncio.gather(*tasks, return_exceptions=True)

    def _build_provider(self, browser: Browser) -> GoogleFlightsProvider:
        fetcher = GoogleFlightsBrowserFetcher(browser=browser)
        return GoogleFlightsProvider(fetcher=fetcher)