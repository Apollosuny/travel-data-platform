import asyncio
import logging
import re

from fast_flights import FlightData, Passengers, get_flights
from fast_flights.schema import Flight, Result

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.exceptions import ProviderFetchError
from travel_data_platform.providers.google_flights.fetchers.base import (
    GoogleFlightsRawFetcher,
)

_CURRENCY_BY_SYMBOL: list[tuple[str, str]] = [
    ("₫", "VND"),
    ("VND", "VND"),
    ("$", "USD"),
    ("USD", "USD"),
    ("€", "EUR"),
    ("EUR", "EUR"),
    ("£", "GBP"),
    ("GBP", "GBP"),
    ("¥", "JPY"),
    ("JPY", "JPY"),
]


class GoogleFlightsTfsFetcher(GoogleFlightsRawFetcher):
    """Fetches Google Flights offers via the `tfs` deeplink approach.

    Wraps the synchronous `fast_flights.get_flights` call in `asyncio.to_thread`
    so it composes with the rest of the async ingestion pipeline.
    """

    def __init__(
        self,
        seat: str = "economy",
        fetch_mode: str = "common",
        max_offers: int | None = None,
    ) -> None:
        self._seat = seat
        self._fetch_mode = fetch_mode
        self._max_offers = max_offers
        self._logger = logging.getLogger(__name__)

    async def fetch_raw(self, query: FlightQuery) -> list[dict]:
        try:
            result = await asyncio.to_thread(self._do_fetch, query)
        except ProviderFetchError:
            raise
        except RuntimeError as exc:
            # fast_flights raises RuntimeError("No flights found:\n...") when the
            # Google Flights page renders but has no offers — typically because
            # the airline schedule for that date is not yet published (booking
            # horizon for low-frequency routes is ~45-60 days). This is a normal
            # transient state, not a fetch failure: return zero offers and let
            # the next batch run pick up inventory once it appears.
            if str(exc).startswith("No flights found"):
                self._logger.info(
                    "tfs_no_inventory origin=%s destination=%s departure=%s return=%s",
                    query.origin,
                    query.destination,
                    query.departure_date,
                    query.return_date,
                )
                return []
            raise ProviderFetchError(
                "fast_flights call failed for Google Flights TFS fetcher"
            ) from exc
        except Exception as exc:
            raise ProviderFetchError(
                "fast_flights call failed for Google Flights TFS fetcher"
            ) from exc

        offers: list[dict] = []
        for flight in result.flights:
            offer = self._normalize_flight(flight)
            if offer is None:
                continue
            offers.append(offer)
            if self._max_offers is not None and len(offers) >= self._max_offers:
                break

        self._logger.info(
            "tfs_fetch_completed origin=%s destination=%s departure=%s return=%s "
            "offers=%s current_price=%s",
            query.origin,
            query.destination,
            query.departure_date,
            query.return_date,
            len(offers),
            result.current_price,
        )
        return offers

    def _do_fetch(self, query: FlightQuery) -> Result:
        flight_data = [
            FlightData(
                date=query.departure_date.isoformat(),
                from_airport=query.origin,
                to_airport=query.destination,
            )
        ]
        if query.return_date is not None:
            flight_data.append(
                FlightData(
                    date=query.return_date.isoformat(),
                    from_airport=query.destination,
                    to_airport=query.origin,
                )
            )

        trip = "round-trip" if query.return_date is not None else "one-way"

        return get_flights(
            flight_data=flight_data,
            trip=trip,
            passengers=Passengers(adults=query.adults),
            seat=self._seat,
            fetch_mode=self._fetch_mode,
        )

    def _normalize_flight(self, flight: Flight) -> dict | None:
        price_info = self._parse_price(flight.price)
        if price_info is None:
            return None

        return {
            "price": price_info["price"],
            "currency": price_info["currency"],
            "airline": flight.name or None,
            "stops": _coerce_stops(flight.stops),
            "duration_text": flight.duration or None,
            "departure_time_text": flight.departure or None,
            "arrival_time_text": flight.arrival or None,
            "card_aria_label": None,
            "source_url": None,
            "tfs_is_best": flight.is_best,
            "tfs_arrival_time_ahead": flight.arrival_time_ahead or None,
            "tfs_delay": flight.delay,
            "tfs_raw_stops": flight.stops,
        }

    def _parse_price(self, value: str | None) -> dict | None:
        if not value:
            return None

        text = value.strip()
        if not text:
            return None

        currency = _detect_currency(text)
        digits = re.sub(r"[^0-9]", "", text)
        if not digits:
            return None

        return {"price": int(digits), "currency": currency}


def _coerce_stops(value: object) -> int | None:
    """fast_flights occasionally returns 'Unknown' or other non-int values for stops.

    The DB column is SMALLINT, so anything non-numeric must be coerced to None.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _detect_currency(text: str) -> str:
    for token, code in _CURRENCY_BY_SYMBOL:
        if token in text:
            return code
    return "VND"
