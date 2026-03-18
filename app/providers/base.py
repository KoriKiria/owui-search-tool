from abc import ABC, abstractmethod

from app.models import SearchProviderResponse


class SearchProvider(ABC):
    name: str

    @abstractmethod
    async def search(self, query: str, count: int, search_engine: str, language: str) -> SearchProviderResponse:
        raise NotImplementedError
