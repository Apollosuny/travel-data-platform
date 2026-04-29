from datetime import date
from unittest.mock import patch

import pytest
from fast_flights.schema import Flight, Result

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.exceptions import ProviderFetchError
from travel_data_platform.providers.google_flights.fetchers.tfs_fetcher import (
    GoogleFlightsTfsFetcher,
)


def _flight(price: str, **overrides) -> Flight:
    base = {
        "is_best": False,
        "name": "Vietnam Airlines",
        "departure": "8:00 AM on Fri, May 1",
        "arrival": "10:30 AM on Fri, May 1",
        "arrival_time_ahead": "",
        "duration": "2 hr 30 min",
        "stops": 0,
        "delay": None,
        "price": price,
    }
    base.update(overrides)
    return Flight(**base)


def test_parse_price_vnd_with_currency_symbol():
    fetcher = GoogleFlightsTfsFetcher()

    assert fetcher._parse_price("5,986,000 ₫") == {
        "price": 5986000,
        "currency": "VND",
    }


def test_parse_price_usd():
    fetcher = GoogleFlightsTfsFetcher()

    assert fetcher._parse_price("$120") == {"price": 120, "currency": "USD"}


def test_parse_price_returns_none_for_empty_or_no_digits():
    fetcher = GoogleFlightsTfsFetcher()

    assert fetcher._parse_price("") is None
    assert fetcher._parse_price(None) is None
    assert fetcher._parse_price("free") is None


def test_normalize_flight_maps_canonical_fields():
    fetcher = GoogleFlightsTfsFetcher()

    offer = fetcher._normalize_flight(
        _flight(price="5,986,000 ₫", stops=1, name="VietJet Air")
    )

    assert offer is not None
    assert offer["price"] == 5986000
    assert offer["currency"] == "VND"
    assert offer["airline"] == "VietJet Air"
    assert offer["stops"] == 1
    assert offer["duration_text"] == "2 hr 30 min"
    assert offer["departure_time_text"].startswith("8:00 AM")
    assert offer["arrival_time_text"].startswith("10:30 AM")
    assert offer["tfs_is_best"] is False


def test_normalize_flight_coerces_unknown_stops_to_none():
    fetcher = GoogleFlightsTfsFetcher()

    offer = fetcher._normalize_flight(_flight(price="2,499,000 ₫", stops="Unknown"))

    assert offer is not None
    assert offer["stops"] is None
    assert offer["tfs_raw_stops"] == "Unknown"


def test_normalize_flight_returns_none_when_price_unparseable():
    fetcher = GoogleFlightsTfsFetcher()

    assert fetcher._normalize_flight(_flight(price="")) is None


@pytest.mark.asyncio
async def test_fetch_raw_uses_round_trip_when_return_date_set():
    fetcher = GoogleFlightsTfsFetcher()
    captured_kwargs: dict = {}

    def fake_get_flights(**kwargs):
        captured_kwargs.update(kwargs)
        return Result(
            current_price="typical",
            flights=[_flight(price="2,350,000 ₫")],
        )

    query = FlightQuery(
        origin="HAN",
        destination="BKK",
        departure_date=date(2026, 8, 7),
        return_date=date(2026, 8, 9),
    )

    with patch(
        "travel_data_platform.providers.google_flights.fetchers.tfs_fetcher.get_flights",
        side_effect=fake_get_flights,
    ):
        offers = await fetcher.fetch_raw(query)

    assert len(offers) == 1
    assert offers[0]["price"] == 2350000
    assert captured_kwargs["trip"] == "round-trip"
    assert len(captured_kwargs["flight_data"]) == 2
    assert captured_kwargs["flight_data"][0].from_airport == "HAN"
    assert captured_kwargs["flight_data"][1].from_airport == "BKK"


@pytest.mark.asyncio
async def test_fetch_raw_uses_one_way_when_no_return_date():
    fetcher = GoogleFlightsTfsFetcher()
    captured_kwargs: dict = {}

    def fake_get_flights(**kwargs):
        captured_kwargs.update(kwargs)
        return Result(current_price="low", flights=[])

    query = FlightQuery(
        origin="SGN",
        destination="BKK",
        departure_date=date(2026, 6, 1),
    )

    with patch(
        "travel_data_platform.providers.google_flights.fetchers.tfs_fetcher.get_flights",
        side_effect=fake_get_flights,
    ):
        offers = await fetcher.fetch_raw(query)

    assert offers == []
    assert captured_kwargs["trip"] == "one-way"
    assert len(captured_kwargs["flight_data"]) == 1


@pytest.mark.asyncio
async def test_fetch_raw_wraps_lib_errors_in_provider_fetch_error():
    fetcher = GoogleFlightsTfsFetcher()

    def boom(**_kwargs):
        raise RuntimeError("upstream blew up")

    query = FlightQuery(
        origin="HAN",
        destination="BKK",
        departure_date=date(2026, 8, 7),
    )

    with patch(
        "travel_data_platform.providers.google_flights.fetchers.tfs_fetcher.get_flights",
        side_effect=boom,
    ), pytest.raises(ProviderFetchError):
        await fetcher.fetch_raw(query)


@pytest.mark.asyncio
async def test_fetch_raw_respects_max_offers():
    fetcher = GoogleFlightsTfsFetcher(max_offers=2)

    def fake_get_flights(**_kwargs):
        return Result(
            current_price="typical",
            flights=[_flight(price=f"{p},000 ₫") for p in [1000, 2000, 3000, 4000]],
        )

    query = FlightQuery(
        origin="HAN",
        destination="BKK",
        departure_date=date(2026, 8, 7),
    )

    with patch(
        "travel_data_platform.providers.google_flights.fetchers.tfs_fetcher.get_flights",
        side_effect=fake_get_flights,
    ):
        offers = await fetcher.fetch_raw(query)

    assert len(offers) == 2
