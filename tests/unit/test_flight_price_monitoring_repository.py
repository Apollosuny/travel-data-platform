import uuid
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from travel_data_platform.database.models.flight_watch import FlightWatch
from travel_data_platform.database.models.normalized_flight_offer import (
    NormalizedFlightOffer,
)
from travel_data_platform.repositories.flight_price_monitoring_repository import (
    _apply_watch_offer_filters,
)


def _watch(**overrides) -> FlightWatch:
    fields = {
        "id": uuid.uuid4(),
        "origin": "KUL",
        "destination": "HAN",
        "departure_date": date(2026, 11, 24),
        "return_date": None,
        "adults": 1,
        "departure_time_from": None,
        "departure_time_to": None,
        "max_stops": None,
    }
    fields.update(overrides)
    return FlightWatch(**fields)


def _compiled_where(watch: FlightWatch) -> tuple[str, dict]:
    stmt = _apply_watch_offer_filters(select(NormalizedFlightOffer), watch)
    compiled = stmt.compile(dialect=postgresql.dialect())
    where_sql = str(compiled).split("WHERE", 1)[1] if "WHERE" in str(compiled) else ""
    return where_sql, compiled.params


def test_no_filters_leaves_query_unrestricted():
    where_sql, params = _compiled_where(_watch())

    assert where_sql == ""
    assert params == {}


def test_departure_window_and_max_stops_are_applied():
    watch = _watch(departure_time_from=time(18, 0), departure_time_to=time(18, 30), max_stops=0)

    where_sql, params = _compiled_where(watch)

    assert "departure_time_local >=" in where_sql
    assert "departure_time_local <=" in where_sql
    assert "stops <=" in where_sql
    assert sorted(params.values(), key=str) == sorted([time(18, 0), time(18, 30), 0], key=str)


def test_single_sided_window_only_adds_that_bound():
    where_sql, params = _compiled_where(_watch(departure_time_from=time(17, 0)))

    assert "departure_time_local >=" in where_sql
    assert "departure_time_local <=" not in where_sql
    assert "stops" not in where_sql
    assert list(params.values()) == [time(17, 0)]
