from datetime import date, timedelta

from sqlalchemy import and_, not_, select, tuple_

from travel_data_platform.database.models.flight_watch import FlightWatch
from travel_data_platform.database.session import SessionLocal

ORIGIN = "HAN"
DESTINATION = "VCL"
TRIP_NIGHTS = 3
ADULTS = 4

# Target is 3,500,000 VND per person. Google Flights (and fast_flights) return the
# total price for the queried passenger count, so the stored target must be
# multiplied by ADULTS to keep AlertRuleEvaluator.BELOW_TARGET semantics correct.
TARGET_PRICE_PER_ADULT = 3_500_000
TARGET_PRICE_TOTAL = TARGET_PRICE_PER_ADULT * ADULTS

CHECK_FREQUENCY_MINUTES = 360

# Departure must be in July 2026; trip is 3 nights anchored on Thursday or Friday.
# Return may slip into early August for the last week of July.
DEPARTURE_MONTH_YEAR = (2026, 7)
DEPARTURE_WEEKDAYS = (3, 4)  # Mon=0 ... Thu=3, Fri=4


def _build_watches() -> list[FlightWatch]:
    year, month = DEPARTURE_MONTH_YEAR
    watches: list[FlightWatch] = []
    current = date(year, month, 1)
    while current.month == month:
        if current.weekday() in DEPARTURE_WEEKDAYS:
            watches.append(
                FlightWatch(
                    origin=ORIGIN,
                    destination=DESTINATION,
                    departure_date=current,
                    return_date=current + timedelta(days=TRIP_NIGHTS),
                    adults=ADULTS,
                    target_price=TARGET_PRICE_TOTAL,
                    is_active=True,
                    check_frequency_minutes=CHECK_FREQUENCY_MINUTES,
                )
            )
        current += timedelta(days=1)
    return watches


def main() -> None:
    db = SessionLocal()
    try:
        desired = _build_watches()
        desired_keys = {
            (w.origin, w.destination, w.departure_date, w.return_date, w.adults)
            for w in desired
        }

        # Cleanup: delete any existing watches on the same route that are not
        # in the new desired set. flight_alert_events has ON DELETE CASCADE,
        # so historical alerts for stale watches are removed with them.
        stale = db.execute(
            select(FlightWatch).where(
                and_(
                    FlightWatch.origin == ORIGIN,
                    FlightWatch.destination == DESTINATION,
                    not_(
                        tuple_(
                            FlightWatch.origin,
                            FlightWatch.destination,
                            FlightWatch.departure_date,
                            FlightWatch.return_date,
                            FlightWatch.adults,
                        ).in_(list(desired_keys))
                    ),
                )
            )
        ).scalars().all()

        deleted = len(stale)
        for row in stale:
            db.delete(row)

        inserted = 0
        updated = 0
        for watch in desired:
            existing = db.execute(
                select(FlightWatch).where(
                    FlightWatch.origin == watch.origin,
                    FlightWatch.destination == watch.destination,
                    FlightWatch.departure_date == watch.departure_date,
                    FlightWatch.return_date == watch.return_date,
                    FlightWatch.adults == watch.adults,
                )
            ).scalar_one_or_none()

            if existing is None:
                db.add(watch)
                inserted += 1
            else:
                existing.target_price = watch.target_price
                existing.is_active = watch.is_active
                existing.check_frequency_minutes = watch.check_frequency_minutes
                updated += 1

        db.commit()
        print(
            f"seeded route={ORIGIN}-{DESTINATION} "
            f"month={DEPARTURE_MONTH_YEAR[0]}-{DEPARTURE_MONTH_YEAR[1]:02d} "
            f"nights={TRIP_NIGHTS} adults={ADULTS} "
            f"target_total={TARGET_PRICE_TOTAL} "
            f"inserted={inserted} updated={updated} deleted={deleted} "
            f"total={len(desired)}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
