from pydantic import BaseModel


class AlertCandidate(BaseModel):
    alert_type: str
    current_price: int
    currency: str
    baseline_price: int | None = None
    target_price: int | None = None
    message: str
