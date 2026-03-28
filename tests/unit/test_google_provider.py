import pytest

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.providers.google_flights.client import GoogleFlightsProvider
from travel_data_platform.providers.google_flights.fetchers.base import GoogleFlightsRawFetcher


class FakeGoogleFlightsFetcher(GoogleFlightsRawFetcher):
    async def fetch_raw(self, query: FlightQuery) -> list[dict]:
        return [
            {
                "price": 2350000,
                "currency": "VND",
                "airline": "VietJet Air",
                "stops": 0,
                "duration_text": "1 hr 50 min",
                "departure_time_text": "11:10 AM",
                "arrival_time_text": "1:00 PM",
                "card_aria_label": "Fake offer 1",
                "source_url": "https://example.com",
            },
            {
                "price": 2890000,
                "currency": "VND",
                "airline": "Thai AirAsia",
                "stops": 1,
                "duration_text": "3 hr 20 min",
                "departure_time_text": "8:00 AM",
                "arrival_time_text": "11:20 AM",
                "card_aria_label": "Fake offer 2",
                "source_url": "https://example.com",
            },
        ]


@pytest.mark.asyncio
async def test_google_provider_returns_offers():
    provider = GoogleFlightsProvider(fetcher=FakeGoogleFlightsFetcher())

    query = FlightQuery(
        origin="HAN",
        destination="BKK",
        departure_date="2026-04-20",
    )

    offers = await provider.search(query)

    assert len(offers) == 2
    assert offers[0].price == 2350000
    assert offers[0].currency == "VND"
    assert offers[0].airline == "VietJet Air"
    assert offers[0].stops == 0
    assert offers[1].airline == "Thai AirAsia"
    assert offers[1].stops == 1