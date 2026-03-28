from abc import ABC, abstractmethod
from travel_data_platform.domain.flight import FlightOffer, FlightQuery

class FlightProvider(ABC): 
  @abstractmethod
  async def search(self, query: FlightQuery) -> list[FlightOffer]:
    raise NotImplementedError