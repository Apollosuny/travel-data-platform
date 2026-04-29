from travel_data_platform.domain.flight import FlightOffer, FlightQuery
from travel_data_platform.providers.base import FlightProvider
from travel_data_platform.providers.google_flights.fetchers.base import GoogleFlightsRawFetcher
from travel_data_platform.providers.google_flights.fetchers.tfs_fetcher import (
    GoogleFlightsTfsFetcher,
)
from travel_data_platform.providers.google_flights.parser import parse_offers


class GoogleFlightsProvider(FlightProvider):
    def __init__(self, fetcher: GoogleFlightsRawFetcher | None = None) -> None:
        self.fetcher = fetcher or GoogleFlightsTfsFetcher()

    async def search(self, query: FlightQuery) -> list[FlightOffer]:
        raw_offers = await self.fetcher.fetch_raw(query)
        return parse_offers(raw_offers)