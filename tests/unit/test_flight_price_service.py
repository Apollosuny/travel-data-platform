from datetime import date, timedelta

import pytest

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.services.flight_price_service import FlightPriceService


@pytest.mark.asyncio
async def test_flight_price_service_fetches_prices():
    service = FlightPriceService()

    query = FlightQuery(
        origin="HAN",
        destination="BKK",
        departure_date=date.today() + timedelta(days=30),
    )

    offers = await service.fetch_prices(query)

    assert len(offers) > 0