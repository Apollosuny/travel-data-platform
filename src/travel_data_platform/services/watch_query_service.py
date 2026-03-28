from travel_data_platform.database.models.flight_watch import FlightWatch
from travel_data_platform.domain.flight import FlightQuery


class WatchQueryService:
    def to_query(self, watch: FlightWatch) -> FlightQuery:
        return FlightQuery(
            origin=watch.origin,
            destination=watch.destination,
            departure_date=watch.departure_date,
            return_date=watch.return_date,
            adults=watch.adults,
        )