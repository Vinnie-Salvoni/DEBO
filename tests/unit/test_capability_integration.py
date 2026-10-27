from datetime import UTC, datetime

from desk_robot.core.capabilities import Capability, CapabilityStatus
from desk_robot.information import InformationError, NewsArticle, NewsReport, WeatherReport
from desk_robot.robot import DeskRobot


class WorkingWeather:
    def fetch_current(self, location: str) -> WeatherReport:
        return WeatherReport(location, 12.0, "Cloudy", "fake", datetime.now(UTC))


class BrokenWeather:
    def fetch_current(self, location: str) -> WeatherReport:
        raise InformationError("Weather provider unavailable.")


class WorkingNews:
    def fetch_latest(self, limit: int = 5) -> NewsReport:
        return NewsReport("fake", datetime.now(UTC), (NewsArticle("A headline", "Test", "https://example.com"),))


class EmptyNews:
    def fetch_latest(self, limit: int = 5) -> NewsReport:
        return NewsReport("fake", datetime.now(UTC), ())


def test_successful_weather_updates_only_weather_capability() -> None:
    robot = DeskRobot(weather_provider=WorkingWeather())
    robot.respond("weather in London")
    assert robot.capabilities.get(Capability.WEATHER).status is CapabilityStatus.AVAILABLE
    assert robot.capabilities.get(Capability.OLLAMA).status is CapabilityStatus.UNKNOWN
    assert robot.capabilities.get(Capability.INTERNET).status is CapabilityStatus.UNKNOWN


def test_weather_provider_failure_is_visible_in_capability_state() -> None:
    robot = DeskRobot(weather_provider=BrokenWeather())
    robot.respond("weather in London")
    status = robot.capabilities.get(Capability.WEATHER)
    assert status.status is CapabilityStatus.UNAVAILABLE
    assert status.detail == "Weather provider unavailable."


def test_news_empty_result_is_not_marked_available() -> None:
    robot = DeskRobot(news_provider=EmptyNews())
    robot.respond("show me the news")
    assert robot.capabilities.get(Capability.NEWS).status is CapabilityStatus.UNAVAILABLE


def test_news_success_marks_news_available() -> None:
    robot = DeskRobot(news_provider=WorkingNews())
    robot.respond("show me the news")
    assert robot.capabilities.get(Capability.NEWS).status is CapabilityStatus.AVAILABLE
