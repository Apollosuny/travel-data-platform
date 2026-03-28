from pydantic import BaseModel

class FlightQuery(BaseModel):
  origin: str
  destination: str
  departure_date: str
  return_date: str | None = None
  adults: int = 1

class FlightOffer(BaseModel):
  price: int
  currency: str
  airline: str | None = None
  stops: int | None = None
  