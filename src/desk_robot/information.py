from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol

import feedparser
import requests


@dataclass(frozen=True)
class WeatherReport:
    """Current weather and the source/time of the information."""

    location: str
    temperature_c: float
    condition: str
    provider: str
    fetched_at: datetime
    observed_at: datetime | None = None
    daily_high_c: float | None = None
    daily_low_c: float | None = None
    forecast_condition: str | None = None


@dataclass(frozen=True)
class NewsArticle:
    """A news article from an RSS source."""

    title: str
    source: str
    url: str
    published_at: datetime | None = None


@dataclass(frozen=True)
class NewsReport:
    """A collection of headlines and retrieval metadata."""

    provider: str
    fetched_at: datetime
    articles: tuple[NewsArticle, ...]


class WeatherProvider(Protocol):
    def fetch_current(self, location: str) -> WeatherReport:
        """Fetch current weather for a location."""


class NewsProvider(Protocol):
    def fetch_latest(self, limit: int = 5) -> NewsReport:
        """Fetch a limited number of recent articles."""


class InformationError(RuntimeError):
    """Raised when an information provider cannot return usable data."""


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        except TypeError, ValueError, OverflowError:
            return None


def _weather_condition(code: int) -> str:
    """Convert WMO weather interpretation codes into readable conditions."""
    if code == 0:
        return "Clear sky"
    if code in {1, 2}:
        return "Mainly clear"
    if code == 3:
        return "Overcast"
    if code in {45, 48}:
        return "Fog"
    if code in {51, 53, 55}:
        return "Drizzle"
    if code in {56, 57}:
        return "Freezing drizzle"
    if code in {61, 63, 65}:
        return "Rain"
    if code in {66, 67}:
        return "Freezing rain"
    if code in {71, 73, 75, 77}:
        return "Snow"
    if code in {80, 81, 82}:
        return "Rain showers"
    if code in {85, 86}:
        return "Snow showers"
    if code == 95:
        return "Thunderstorm"
    if code in {96, 99}:
        return "Thunderstorm with hail"
    return "Conditions unavailable"


class OpenMeteoWeatherProvider:
    """Current weather using Open-Meteo geocoding and forecast APIs."""

    name = "Open-Meteo"

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout

    def fetch_current(self, location: str) -> WeatherReport:
        location = location.strip()
        if not location:
            raise InformationError("Please provide a location for the weather.")

        try:
            geo_response = requests.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={
                    "name": location,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                },
                timeout=self.timeout,
            )
            geo_response.raise_for_status()
            locations = geo_response.json().get("results", [])

            if not locations:
                raise InformationError(f"I couldn't find a place called {location}.")

            place = locations[0]
            latitude = place["latitude"]
            longitude = place["longitude"]
            place_name = place["name"]
            if place.get("admin1"):
                place_name = f"{place_name}, {place['admin1']}"
            if place.get("country"):
                place_name = f"{place_name}, {place['country']}"

            weather_response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                    "forecast_days": 1,
                    "timezone": "auto",
                },
                timeout=self.timeout,
            )
            weather_response.raise_for_status()
            payload = weather_response.json()
            current = payload.get("current")
            if not isinstance(current, dict):
                raise InformationError(
                    "The weather service returned no current conditions."
                )

            temperature = current.get("temperature_2m")
            code = current.get("weather_code")
            if temperature is None or code is None:
                raise InformationError(
                    "The weather service returned incomplete conditions."
                )

            observed_at = _parse_datetime(current.get("time"))
            daily = payload.get("daily")
            high = low = forecast_condition = None
            if isinstance(daily, dict):
                try:
                    highs = daily.get("temperature_2m_max") or []
                    lows = daily.get("temperature_2m_min") or []
                    codes = daily.get("weather_code") or []
                    if highs and lows and highs[0] is not None and lows[0] is not None:
                        high, low = float(highs[0]), float(lows[0])
                    if codes and codes[0] is not None:
                        forecast_condition = _weather_condition(int(codes[0]))
                except (TypeError, ValueError, IndexError):
                    high = low = forecast_condition = None
            return WeatherReport(
                location=place_name,
                temperature_c=float(temperature),
                condition=_weather_condition(int(code)),
                provider=self.name,
                fetched_at=datetime.now(UTC),
                observed_at=observed_at,
                daily_high_c=high,
                daily_low_c=low,
                forecast_condition=forecast_condition,
            )
        except InformationError:
            raise
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            raise InformationError(
                "I couldn't retrieve the weather just now. Please try again."
            ) from error


class RssNewsProvider:
    """Fetch headlines from a configurable RSS feed."""

    def __init__(
        self,
        feed_url: str = "https://feeds.bbci.co.uk/news/uk/rss.xml",
        provider_name: str = "BBC News UK RSS",
        timeout: float = 8.0,
    ) -> None:
        self.feed_url = feed_url
        self.provider_name = provider_name
        self.timeout = timeout

    def fetch_latest(self, limit: int = 5) -> NewsReport:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        limit = min(limit, 20)

        try:
            response = requests.get(
                self.feed_url,
                headers={"User-Agent": "DEBO-Desk-Companion/0.1"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            parsed = feedparser.parse(response.content)

            if parsed.bozo and not parsed.entries:
                raise InformationError("The news feed could not be read.")

            articles: list[NewsArticle] = []
            for entry in parsed.entries[:limit]:
                title = str(entry.get("title", "")).strip()
                url = str(entry.get("link", "")).strip()
                if not title or not url:
                    continue

                published = None
                if entry.get("published"):
                    published = _parse_datetime(entry.get("published"))
                elif entry.get("updated"):
                    published = _parse_datetime(entry.get("updated"))

                articles.append(
                    NewsArticle(
                        title=title,
                        source=self.provider_name,
                        url=url,
                        published_at=published,
                    )
                )

            if not articles:
                raise InformationError("The news feed returned no usable headlines.")

            return NewsReport(
                provider=self.provider_name,
                fetched_at=datetime.now(UTC),
                articles=tuple(articles),
            )
        except InformationError:
            raise
        except requests.RequestException as error:
            raise InformationError(
                "I couldn't retrieve the news just now. Please try again."
            ) from error
