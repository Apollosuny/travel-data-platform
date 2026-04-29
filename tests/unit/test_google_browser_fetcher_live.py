from datetime import date, timedelta

import pytest

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.providers.google_flights.fetchers.browser_fetcher import (
    GoogleFlightsBrowserFetcher,
)


@pytest.mark.asyncio
async def test_google_browser_fetcher_live():
    fetcher = GoogleFlightsBrowserFetcher()

    query = FlightQuery(
        origin="HAN",
        destination="BKK",
        departure_date=date.today() + timedelta(days=30),
    )

    raw_offers = await fetcher.fetch_raw(query)

    assert len(raw_offers) > 0
    assert raw_offers[0]["price"] > 0