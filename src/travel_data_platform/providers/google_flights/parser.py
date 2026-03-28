from travel_data_platform.domain.flight import FlightOffer
from travel_data_platform.exceptions import ProviderParseError
from travel_data_platform.providers.google_flights.schemas import GoogleFlightsRawOffer


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
                )
            )
    except Exception as exc:
        raise ProviderParseError("Failed to parse Google Flights raw offers") from exc

    return offers