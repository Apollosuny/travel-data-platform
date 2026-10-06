from datetime import time

import pytest

from travel_data_platform.providers.google_flights.parser import parse_clock_time, parse_offers


def test_parse_offers():
    raw_offers = [
        {
            "price": 2350000,
            "currency": "VND",
            "airline": "VietJet Air",
            "stops": 0,
        }
    ]

    offers = parse_offers(raw_offers)

    assert len(offers) == 1
    assert offers[0].price == 2350000
    assert offers[0].currency == "VND"
    assert offers[0].airline == "VietJet Air"
    assert offers[0].departure_time_local is None
    assert offers[0].arrival_time_local is None


def test_parse_offers_extracts_local_times():
    raw_offers = [
        {
            "price": 2291905,
            "currency": "VND",
            "airline": "AirAsia",
            "stops": 0,
            "departure_time_text": "Departure time: 6:10 PM.",
            "arrival_time_text": "Arrival time: 10:25 AM on  Wednesday, November 25.",
        }
    ]

    offers = parse_offers(raw_offers)

    assert offers[0].departure_time_local == time(18, 10)
    assert offers[0].arrival_time_local == time(10, 25)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Departure time: 6:10 PM.", time(18, 10)),
        ("6:10 PM on Tue, Nov 24", time(18, 10)),
        ("6:10 AM on Tue, Nov 24", time(6, 10)),
        ("12:00 PM on Tue, Nov 24", time(12, 0)),
        ("12:05 AM", time(0, 5)),
        ("6:10 PM", time(18, 10)),
        ("18:10", time(18, 10)),
        ("00:30", time(0, 30)),
    ],
)
def test_parse_clock_time_supported_formats(text: str, expected: time):
    assert parse_clock_time(text) == expected


@pytest.mark.parametrize("text", [None, "", "Departure time unavailable", "13:10 PM", "25:00"])
def test_parse_clock_time_returns_none_for_invalid_input(text: str | None):
    assert parse_clock_time(text) is None
