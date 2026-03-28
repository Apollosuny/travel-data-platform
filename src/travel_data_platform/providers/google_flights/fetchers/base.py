from abc import ABC, abstractmethod

from travel_data_platform.domain.flight import FlightQuery

class GoogleFlightsRawFetcher(ABC):
  @abstractmethod
  async def fetch_raw(self, query: FlightQuery) -> list[dict]:
    raise NotImplementedError