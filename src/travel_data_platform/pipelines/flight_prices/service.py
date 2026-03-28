from travel_data_platform.providers.base import FlightQuery
from travel_data_platform.providers.google_flights.client import GoogleFlightsProvider


class FlightPriceService:
    def __init__(self) -> None:
        self.provider = GoogleFlightsProvider()

    async def fetch_prices(self, query: FlightQuery):
        return await self.provider.search(query)