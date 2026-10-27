from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from desk_robot.information import (
    InformationError,
    NewsArticle,
    OpenMeteoWeatherProvider,
    RssNewsProvider,
    _parse_datetime,
)


def test_parse_datetime_normalizes_naive_iso_values_to_utc() -> None:
    parsed = _parse_datetime("2026-10-27T12:30:00")
    assert parsed is not None
    assert parsed.tzinfo is UTC


def test_parse_datetime_returns_none_for_invalid_input() -> None:
    assert _parse_datetime("not a date") is None


def test_weather_provider_rejects_blank_location_without_network() -> None:
    with pytest.raises(InformationError, match="provide a location"):
        OpenMeteoWeatherProvider().fetch_current("   ")


def test_news_provider_rejects_non_positive_limit_without_network() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        RssNewsProvider().fetch_latest(0)


def test_story_reader_rejects_non_http_urls_without_network() -> None:
    provider = RssNewsProvider()
    article = NewsArticle("Headline", "Source", "file:///etc/passwd")
    with pytest.raises(InformationError, match="valid web address"):
        provider.fetch_story(article)


def test_weather_provider_translates_http_failure_to_information_error(monkeypatch) -> None:
    response = Mock()
    response.raise_for_status.side_effect = __import__("requests").RequestException("offline")
    monkeypatch.setattr("desk_robot.information.requests.get", Mock(return_value=response))
    with pytest.raises(InformationError, match="retrieve the weather"):
        OpenMeteoWeatherProvider().fetch_current("London")


def test_news_provider_translates_http_failure_to_information_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "desk_robot.information.requests.get",
        Mock(side_effect=__import__("requests").RequestException("offline")),
    )
    with pytest.raises(InformationError, match="retrieve the news"):
        RssNewsProvider().fetch_latest()


def test_story_reader_translates_http_failure_to_information_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "desk_robot.information.requests.get",
        Mock(side_effect=__import__("requests").RequestException("offline")),
    )
    article = NewsArticle("Headline", "Source", "https://example.com/story")
    with pytest.raises(InformationError, match="download that story"):
        RssNewsProvider().fetch_story(article)
