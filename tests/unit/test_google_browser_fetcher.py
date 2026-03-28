from travel_data_platform.providers.google_flights.fetchers.browser_fetcher import (
    GoogleFlightsBrowserFetcher,
)


def test_parse_price_from_vietnamese_dong_label():
    fetcher = GoogleFlightsBrowserFetcher()

    result = fetcher._parse_price("5986000 Vietnamese dong")

    assert result is not None
    assert result["price"] == 5986000
    assert result["currency"] == "VND"


def test_parse_nonstop():
    fetcher = GoogleFlightsBrowserFetcher()

    assert fetcher._parse_stops(
        "From 5986000 Vietnamese dong round trip total. Nonstop flight with Vietnam Airlines."
    ) == 0


def test_parse_one_stop():
    fetcher = GoogleFlightsBrowserFetcher()

    assert fetcher._parse_stops(
        "From 8170000 Vietnamese dong round trip total. 1 stop flight with Vietnam Airlines."
    ) == 1


def test_parse_time_range():
    fetcher = GoogleFlightsBrowserFetcher()

    departure, arrival = fetcher._parse_time_range("7:05 PM – 9:05 PM")

    assert departure == "7:05 PM"
    assert arrival == "9:05 PM"