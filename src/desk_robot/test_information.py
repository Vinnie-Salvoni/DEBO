from datetime import UTC, datetime

from desk_robot.information import (
    NewsArticle,
    NewsReport,
    WeatherReport,
)


def test_weather_report_stores_provider_and_timestamps() -> None:
    fetched_at = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    observed_at = datetime(2026, 10, 26, 11, 55, tzinfo=UTC)

    report = WeatherReport(
        location="London",
        temperature_c=14.5,
        condition="Cloudy",
        provider="FakeWeather",
        fetched_at=fetched_at,
        observed_at=observed_at,
    )

    assert report.location == "London"
    assert report.temperature_c == 14.5
    assert report.provider == "FakeWeather"
    assert report.fetched_at == fetched_at
    assert report.observed_at == observed_at


def test_weather_report_can_have_no_observation_time() -> None:
    report = WeatherReport(
        location="London",
        temperature_c=14.5,
        condition="Cloudy",
        provider="FakeWeather",
        fetched_at=datetime(2026, 10, 26, 12, 0, tzinfo=UTC),
    )

    assert report.observed_at is None


def test_news_report_stores_articles_and_retrieval_time() -> None:
    fetched_at = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    published_at = datetime(2026, 10, 26, 11, 30, tzinfo=UTC)

    article = NewsArticle(
        title="Example headline",
        source="Example News",
        url="https://example.com/news/1",
        published_at=published_at,
    )
    report = NewsReport(
        provider="FakeNews",
        fetched_at=fetched_at,
        articles=(article,),
    )

    assert report.provider == "FakeNews"
    assert report.fetched_at == fetched_at
    assert len(report.articles) == 1
    assert report.articles[0].title == "Example headline"
    assert report.articles[0].published_at == published_at


def test_news_article_can_have_no_publication_time() -> None:
    article = NewsArticle(
        title="Example headline",
        source="Example News",
        url="https://example.com/news/1",
    )

    assert article.published_at is None


def test_empty_news_result_is_representable() -> None:
    report = NewsReport(
        provider="FakeNews",
        fetched_at=datetime(2026, 10, 26, 12, 0, tzinfo=UTC),
        articles=(),
    )

    assert report.articles == ()



def test_weather_report_can_expose_daily_forecast_without_inventing_missing_values() -> None:
    report = WeatherReport(
        location="London",
        temperature_c=14.5,
        condition="Cloudy",
        provider="FakeWeather",
        fetched_at=datetime(2026, 10, 26, 12, 0, tzinfo=UTC),
        daily_high_c=17.0,
        daily_low_c=9.0,
        forecast_condition="Rain showers",
    )

    assert report.daily_high_c == 17.0
    assert report.daily_low_c == 9.0
    assert report.forecast_condition == "Rain showers"


def test_daily_forecast_fields_are_optional() -> None:
    report = WeatherReport(
        location="London",
        temperature_c=14.5,
        condition="Cloudy",
        provider="FakeWeather",
        fetched_at=datetime(2026, 10, 26, 12, 0, tzinfo=UTC),
    )

    assert report.daily_high_c is None
    assert report.daily_low_c is None
    assert report.forecast_condition is None
