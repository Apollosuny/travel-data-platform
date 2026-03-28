from datetime import date
from pydantic import BaseModel

class FlightQuery(BaseModel):
  origin: str
  destination: str
  departure_date: date
  return_date: date | None = None
  adults: int = 1

class FlightOffer(BaseModel):
  price: int
  currency: str
  airline: str | None = None
  stops: int | None = None
  