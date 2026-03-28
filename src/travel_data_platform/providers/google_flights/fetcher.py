from travel_data_platform.domain.flight import FlightQuery


class GoogleFlightsFetcher:
    async def fetch_raw(self, query: FlightQuery) -> list[dict]:
        return [
            {
                "price": 2350000,
                "currency": "VND",
                "airline": "VietJet Air",
                "stops": 0,
            },
            {
                "price": 2890000,
                "currency": "VND",
                "airline": "Thai AirAsia",
                "stops": 1,
            },
        ]