"""One-off probe to isolate fetch issues for a single route.

Usage:
    uv run python -m travel_data_platform.workers.probe_route \
        --origin HAN --destination VCL \
        --departure 2026-07-03 --return 2026-07-06

Runs three independent checks so we can tell *where* the empty-result
problem comes from:

1. Calls `fast_flights.get_flights` directly and prints the raw Result.
2. Calls our `GoogleFlightsTfsFetcher.fetch_raw` and prints normalized dicts.
3. Calls `GoogleFlightsProvider.search` and prints parsed FlightOffer objects.

Nothing is written to the database.
"""

import argparse
import asyncio
import logging
from datetime import date

from fast_flights import FlightData, Passengers, get_flights

from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.logging import setup_logging
from travel_data_platform.providers.google_flights.client import GoogleFlightsProvider
from travel_data_platform.providers.google_flights.fetchers.base import (
    GoogleFlightsRawFetcher,
)
from travel_data_platform.providers.google_flights.fetchers.playwright_fetcher import (
    GoogleFlightsPlaywrightFetcher,
)
from travel_data_platform.providers.google_flights.fetchers.tfs_fetcher import (
    GoogleFlightsTfsFetcher,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="IATA code, e.g. HAN")
    parser.add_argument("--destination", required=True, help="IATA code, e.g. VCL")
    parser.add_argument("--departure", required=True, help="YYYY-MM-DD")
    parser.add_argument("--return", dest="return_date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--seat", default="economy")
    parser.add_argument("--fetch-mode", default="common", help="fast_flights fetch_mode")
    parser.add_argument(
        "--fetcher",
        choices=["tfs", "playwright"],
        default="playwright",
        help="Which raw fetcher to exercise in steps [2] and [3]",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run Playwright with a visible browser window (debug only)",
    )
    return parser.parse_args()


def _build_fetcher(args: argparse.Namespace) -> GoogleFlightsRawFetcher:
    if args.fetcher == "tfs":
        return GoogleFlightsTfsFetcher(fetch_mode=args.fetch_mode)
    return GoogleFlightsPlaywrightFetcher(headless=not args.no_headless)


def _probe_fast_flights_direct(args: argparse.Namespace) -> None:
    print("\n=== [1] fast_flights.get_flights (direct) ===")
    flight_data = [
        FlightData(
            date=args.departure,
            from_airport=args.origin,
            to_airport=args.destination,
        )
    ]
    if args.return_date:
        flight_data.append(
            FlightData(
                date=args.return_date,
                from_airport=args.destination,
                to_airport=args.origin,
            )
        )
    trip = "round-trip" if args.return_date else "one-way"

    try:
        result = get_flights(
            flight_data=flight_data,
            trip=trip,
            passengers=Passengers(adults=args.adults),
            seat=args.seat,
            fetch_mode=args.fetch_mode,
        )
    except Exception as exc:
        print(f"  fast_flights raised {type(exc).__name__}: {exc}")
        return

    print(f"  current_price: {result.current_price}")
    print(f"  flights returned: {len(result.flights)}")
    for idx, flight in enumerate(result.flights[:5], start=1):
        print(
            f"    [{idx}] price={flight.price!r} airline={flight.name!r} "
            f"stops={flight.stops!r} duration={flight.duration!r} "
            f"is_best={flight.is_best}"
        )


async def _probe_fetcher(query: FlightQuery, fetcher: GoogleFlightsRawFetcher) -> None:
    print(f"\n=== [2] {type(fetcher).__name__}.fetch_raw ===")
    try:
        raw = await fetcher.fetch_raw(query)
    except Exception as exc:
        print(f"  fetcher raised {type(exc).__name__}: {exc}")
        return
    print(f"  raw offers: {len(raw)}")
    for idx, offer in enumerate(raw[:5], start=1):
        print(f"    [{idx}] {offer}")


async def _probe_provider(query: FlightQuery, fetcher: GoogleFlightsRawFetcher) -> None:
    print("\n=== [3] GoogleFlightsProvider.search (raw -> parsed) ===")
    provider = GoogleFlightsProvider(fetcher=fetcher)
    try:
        offers = await provider.search(query)
    except Exception as exc:
        print(f"  provider raised {type(exc).__name__}: {exc}")
        return
    print(f"  parsed offers: {len(offers)}")
    for idx, offer in enumerate(offers[:5], start=1):
        print(
            f"    [{idx}] price={offer.price} {offer.currency} "
            f"airline={offer.airline} stops={offer.stops}"
        )


async def _async_main(args: argparse.Namespace) -> None:
    query = FlightQuery(
        origin=args.origin,
        destination=args.destination,
        departure_date=date.fromisoformat(args.departure),
        return_date=date.fromisoformat(args.return_date) if args.return_date else None,
        adults=args.adults,
    )

    print(
        f"Probing route {query.origin}->{query.destination} "
        f"departure={query.departure_date} return={query.return_date} "
        f"adults={query.adults} fetcher={args.fetcher} fetch_mode={args.fetch_mode}"
    )

    await _probe_fetcher(query, _build_fetcher(args))
    await _probe_provider(query, _build_fetcher(args))


def main() -> None:
    setup_logging("DEBUG")
    logging.getLogger("travel_data_platform").setLevel(logging.DEBUG)

    args = _parse_args()
    _probe_fast_flights_direct(args)
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
