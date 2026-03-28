from travel_data_platform.database.models.flight_watch import FlightWatch
from travel_data_platform.database.session import SessionLocal


def main() -> None:
    db = SessionLocal()

    try:
        watches = [
            FlightWatch(
                origin="HAN",
                destination="BKK",
                departure_date="2026-04-20",
                return_date="2026-04-25",
                adults=1,
                target_price=6000000,
                is_active=True,
                check_frequency_minutes=180,
            ),
            FlightWatch(
                origin="SGN",
                destination="BKK",
                departure_date="2026-04-20",
                return_date="2026-04-25",
                adults=1,
                target_price=5000000,
                is_active=True,
                check_frequency_minutes=180,
            ),
        ]

        db.add_all(watches)
        db.commit()
        print("seeded flight watches")
    finally:
        db.close()


if __name__ == "__main__":
    main()