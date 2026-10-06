import re
from datetime import time

from travel_data_platform.domain.flight import FlightOffer
from travel_data_platform.exceptions import ProviderParseError
from travel_data_platform.providers.google_flights.schemas import GoogleFlightsRawOffer

# Matches the first clock time in fetcher output, e.g. "Departure time: 6:10 PM."
# (Playwright aria-label) or "6:10 PM on Tue, Nov 24" (fast_flights). Google may
# separate the AM/PM marker with a narrow no-break space, which `\s` covers.
_CLOCK_TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})(?:\s*([AaPp])\.?[Mm]\.?)?")


def parse_offers(raw_offers: list[dict]) -> list[FlightOffer]:
    offers: list[FlightOffer] = []

    try:
        for item in raw_offers:
            raw = GoogleFlightsRawOffer.model_validate(item)
            offers.append(
                FlightOffer(
                    price=raw.price,
                    currency=raw.currency,
                    airline=raw.airline,
                    stops=raw.stops,
                    departure_time_local=parse_clock_time(raw.departure_time_text),
                    arrival_time_local=parse_clock_time(raw.arrival_time_text),
                )
            )
    except Exception as exc:
        raise ProviderParseError("Failed to parse Google Flights raw offers") from exc

    return offers


def parse_clock_time(text: str | None) -> time | None:
    """Extract a local clock time from free-form fetcher text; None when absent or invalid."""
    if not text:
        return None

    match = _CLOCK_TIME_PATTERN.search(text)
    if match is None:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    meridiem = match.group(3)

    if meridiem is not None:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem.lower() == "p" else 0)

    if hour > 23 or minute > 59:
        return None

    return time(hour, minute)
