import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from travel_data_platform.database.models.flight_alert_event import FlightAlertEvent


class FlightAlertEventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        flight_watch_id: uuid.UUID,
        fetch_run_id: uuid.UUID,
        alert_type: str,
        current_price: int,
        currency: str,
        message: str,
        baseline_price: int | None = None,
        target_price: int | None = None,
        triggered_at: datetime | None = None,
    ) -> FlightAlertEvent:
        row = FlightAlertEvent(
            id=uuid.uuid4(),
            flight_watch_id=flight_watch_id,
            fetch_run_id=fetch_run_id,
            alert_type=alert_type,
            current_price=current_price,
            currency=currency,
            baseline_price=baseline_price,
            target_price=target_price,
            message=message,
            triggered_at=triggered_at or datetime.now(UTC),
            is_read=False,
        )

        self.db.add(row)
        self.db.flush()
        return row
