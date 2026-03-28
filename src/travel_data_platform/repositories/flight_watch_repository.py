import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from travel_data_platform.database.models.flight_watch import FlightWatch


class FlightWatchRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_due_active_watches(self, now: datetime | None = None) -> list[FlightWatch]:
        now = now or datetime.now(UTC)

        stmt: Select[tuple[FlightWatch]] = select(FlightWatch).where(
            FlightWatch.is_active.is_(True)
        )

        rows = self.db.execute(stmt).scalars().all()

        due_watches: list[FlightWatch] = []
        for watch in rows:
            if watch.last_checked_at is None:
                due_watches.append(watch)
                continue

            next_run_at = watch.last_checked_at + timedelta(minutes=watch.check_frequency_minutes)
            if next_run_at <= now:
                due_watches.append(watch)

        return due_watches

    def update_last_checked_at(self, watch_id: uuid.UUID, checked_at: datetime | None = None) -> None:
        checked_at = checked_at or datetime.now(UTC)

        watch = self.db.get(FlightWatch, watch_id)
        if watch is None:
            return

        watch.last_checked_at = checked_at
        self.db.add(watch)
        self.db.flush()