from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class WeatherReport:
    """A current-weather result returned by a weather provider."""

    location: str
    temperature_c: float
    condition: str
    provider: str
    fetched_at: datetime
    observed_at: datetime | None = None


@dataclass(frozen=True)
class NewsArticle:
    """One article returned by a news provider."""

    title: str
    source: str
    url: str
    published_at: datetime | None = None


@dataclass(frozen=True)
class NewsReport:
    """A collection of news articles and retrieval metadata."""

    provider: str
    fetched_at: datetime
    articles: tuple[NewsArticle, ...]


class WeatherProvider(Protocol):
    """Interface implemented by any supported weather service."""

    def fetch_current(self, location: str) -> WeatherReport:
        """Fetch current weather for a location."""
        ...


class NewsProvider(Protocol):
    """Interface implemented by any supported news service."""

    def fetch_latest(self, limit: int = 5) -> NewsReport:
        """Fetch a limited number of recent news articles."""
        ...
