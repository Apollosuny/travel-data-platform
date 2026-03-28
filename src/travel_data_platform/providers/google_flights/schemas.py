from pydantic import BaseModel


class GoogleFlightsRawOffer(BaseModel):
    price: int
    currency: str
    airline: str | None = None
    stops: int | None = None
    duration_text: str | None = None
    departure_time_text: str | None = None
    arrival_time_text: str | None = None
    card_aria_label: str | None = None
    source_url: str | None = None