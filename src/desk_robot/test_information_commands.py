from datetime import UTC, datetime

from desk_robot.information import (
    InformationError,
    NewsArticle,
    NewsReport,
    WeatherReport,
)
from desk_robot.robot import DeskRobot


class FakeWeatherProvider:
    def fetch_current(self, location: str) -> WeatherReport:
        if location.lower() == "nowhere":
            raise InformationError("I couldn't find a place called Nowhere.")

        return WeatherReport(
            location=location,
            temperature_c=14.5,
            condition="Cloudy",
            provider="FakeWeather",
            fetched_at=datetime.now(UTC),
            observed_at=datetime.now(UTC),
        )


class FakeNewsProvider:
    def fetch_latest(self, limit: int = 5) -> NewsReport:
        articles = (
            NewsArticle(
                title="Example headline",
                source="Test News",
                url="https://example.com/news",
            ),
        )
        return NewsReport(
            provider="Test News",
            fetched_at=datetime.now(UTC),
            articles=articles[:limit],
        )


def make_robot() -> DeskRobot:
    return DeskRobot(
        weather_provider=FakeWeatherProvider(),
        news_provider=FakeNewsProvider(),
    )


def test_weather_command_fetches_requested_location() -> None:
    response = make_robot().respond("What's the weather in London?")

    assert "London" in response
    assert "14.5°C" in response
    assert "Cloudy" in response
    assert "FakeWeather" in response


def test_weather_command_asks_for_location_when_missing() -> None:
    response = make_robot().respond("What's the weather?")

    assert "which location" in response.lower()


def test_weather_provider_error_is_reported() -> None:
    response = make_robot().respond("weather in Nowhere")

    assert "couldn't find" in response
    assert "Nowhere" in response


def test_news_command_returns_real_provider_articles() -> None:
    response = make_robot().respond("latest news")

    assert "Test News" in response
    assert "Example headline" in response
    assert "https://example.com/news" in response


def test_existing_recall_still_works() -> None:
    robot = make_robot()
    robot.respond("I saw a strange bird today")

    response = robot.respond("What did I just say?")

    assert "I saw a strange bird today" in response
