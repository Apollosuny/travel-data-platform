from sqlalchemy.orm import Session

from travel_data_platform.database.models.flight_watch import FlightWatch
from travel_data_platform.database.session import SessionLocal
from travel_data_platform.repositories.flight_watch_repository import FlightWatchRepository


class FlightWatchService:
    def list_due_active_watches(self) -> list[FlightWatch]:
        db: Session = SessionLocal()
        try:
            repo = FlightWatchRepository(db)
            return repo.list_due_active_watches()
        finally:
            db.close()