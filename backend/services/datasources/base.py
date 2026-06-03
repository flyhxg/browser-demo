"""Base data source abstraction."""
from abc import ABC, abstractmethod
from typing import Any


class DataSource(ABC):
    """Abstract base class for all data sources."""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def search(self, query: str, **kwargs) -> dict[str, Any]:
        """Execute a search query and return standardized results."""
        ...

    @abstractmethod
    async def health(self) -> bool:
        """Check if the data source is available."""
        ...


class SearchResult:
    """Standardized search result across all data sources."""

    def __init__(
        self,
        source: str,
        query: str,
        data: list[dict],
        metadata: dict | None = None,
    ):
        self.source = source
        self.query = query
        self.data = data
        self.metadata = metadata or {}
