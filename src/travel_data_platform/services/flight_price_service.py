from travel_data_platform.domain.flight import FlightOffer, FlightQuery
from travel_data_platform.providers.base import FlightProvider
from travel_data_platform.providers.google_flights.client import GoogleFlightsProvider


class FlightPriceService:
    def __init__(self, provider: FlightProvider | None = None) -> None:
        self.provider = provider or GoogleFlightsProvider()

    async def fetch_prices(self, query: FlightQuery) -> list[FlightOffer]:
        return await self.provider.search(query)