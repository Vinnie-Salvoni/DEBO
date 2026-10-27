from datetime import UTC, datetime

from desk_robot.core.events import RobotEvent, RobotEventType
from desk_robot.information import InformationError, NewsArticle, NewsReport, WeatherReport
from desk_robot.robot import DeskRobot


class WeatherWorks:
    def fetch_current(self, location: str) -> WeatherReport:
        return WeatherReport(location, 13.0, "Cloudy", "TestWeather", datetime.now(UTC))


class WeatherFails:
    def fetch_current(self, location: str) -> WeatherReport:
        raise InformationError("Weather is unavailable.")


class NewsWorks:
    def fetch_latest(self, limit: int = 5) -> NewsReport:
        article = NewsArticle("Test headline", "Test News", "https://example.com/news")
        return NewsReport("Test News", datetime.now(UTC), (article,))


def test_weather_lookup_emits_semantic_events() -> None:
    events: list[RobotEvent] = []
    robot = DeskRobot(weather_provider=WeatherWorks(), event_sink=events.append)
    robot.respond("weather in London")
    kinds = [event.type for event in events]
    assert RobotEventType.USER_INPUT_RECEIVED in kinds
    assert RobotEventType.WEATHER_LOOKUP_STARTED in kinds
    assert RobotEventType.WEATHER_LOOKUP_SUCCEEDED in kinds
    success = next(event for event in events if event.type is RobotEventType.WEATHER_LOOKUP_SUCCEEDED)
    assert success.data == {"location": "London", "provider": "TestWeather"}


def test_provider_failure_emits_failure_and_capability_events() -> None:
    events: list[RobotEvent] = []
    robot = DeskRobot(weather_provider=WeatherFails(), event_sink=events.append)
    robot.respond("weather in London")
    kinds = [event.type for event in events]
    assert RobotEventType.WEATHER_LOOKUP_FAILED in kinds
    assert RobotEventType.CAPABILITY_CHANGED in kinds


def test_news_lookup_reports_result_count() -> None:
    events: list[RobotEvent] = []
    robot = DeskRobot(news_provider=NewsWorks(), event_sink=events.append)
    robot.respond("show me the news")
    ready = next(event for event in events if event.type is RobotEventType.NEWS_RESULTS_READY)
    assert ready.data == {"article_count": 1, "provider": "Test News"}


def test_event_sink_failure_does_not_break_robot_response() -> None:
    def broken_sink(_event: RobotEvent) -> None:
        raise RuntimeError("display disconnected")

    robot = DeskRobot(event_sink=broken_sink)
    assert "Debo" in robot.respond("what is your name")
