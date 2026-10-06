from datetime import date

from travel_data_platform.database.session import SessionLocal
from travel_data_platform.domain.flight import FlightQuery
from travel_data_platform.repositories.fetch_run_repository import FetchRunRepository


def main() -> None:
    db = SessionLocal()
    try:
        repo = FetchRunRepository(db)

        query = FlightQuery(
            origin="HAN",
            destination="BKK",
            departure_date=date(2026, 4, 20),
            return_date=date(2026, 4, 25),
            adults=1,
        )

        fetch_run = repo.create_running(source="google_flights", query=query)
        db.commit()

        print("created fetch_run:", fetch_run.id)
    finally:
        db.close()


if __name__ == "__main__":
    main()