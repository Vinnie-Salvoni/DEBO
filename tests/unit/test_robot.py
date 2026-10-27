from datetime import UTC, datetime

from desk_robot.context import ConversationContext
from desk_robot.information import (
    InformationError,
    NewsArticle,
    NewsReport,
    WeatherReport,
)
from desk_robot.personality import Personality
from desk_robot.robot import DeskRobot


def test_robot_recalls_previous_user_message() -> None:
    robot = DeskRobot()

    robot.respond("I saw a strange bird today")
    response = robot.respond("What did I just say?")

    assert "I saw a strange bird today" in response


def test_robot_handles_recall_without_history() -> None:
    robot = DeskRobot()

    response = robot.respond("What did I just say?")

    assert "don't have an earlier message" in response


def test_context_is_bounded() -> None:
    context = ConversationContext(max_turns=2)

    context.add_turn("First message", "First reply")
    context.add_turn("Second message", "Second reply")
    context.add_turn("Third message", "Third reply")

    assert len(context.turns) == 2
    assert context.turns[0].user_message == "Second message"
    assert context.last_user_message == "Third message"


def test_context_can_be_cleared() -> None:
    context = ConversationContext()
    context.add_turn("Hello", "Hi!")

    context.clear()

    assert context.turns == ()
    assert context.last_user_message is None


def test_empty_input_does_not_add_context() -> None:
    robot = DeskRobot()
    robot.respond("Hello")
    turns_before = robot.context.turns

    response = robot.respond("   ")

    assert "listening" in response.lower()
    assert robot.context.turns == turns_before


def test_context_limit_must_be_positive() -> None:
    import pytest

    with pytest.raises(ValueError):
        ConversationContext(max_turns=0)


def test_robot_greets_user() -> None:
    robot = DeskRobot()

    response = robot.respond("hello")

    assert "Debo" in response
    assert "Hey!" in response


def test_robot_remembers_its_name() -> None:
    robot = DeskRobot(name="Pip")

    response = robot.respond("what is your name?")

    assert "Pip" in response


def test_robot_handles_empty_input() -> None:
    robot = DeskRobot()

    response = robot.respond("   ")

    assert "listening" in response.lower()
    assert robot.state.turns == 0


def test_robot_counts_nonempty_interactions() -> None:
    robot = DeskRobot()

    robot.respond("hello")
    robot.respond("how are you?")
    robot.respond("something unexpected")

    assert robot.state.turns == 3


def test_robot_handles_unknown_messages() -> None:
    robot = DeskRobot()

    response = robot.respond("I saw a strange bird today")

    assert "Tell me more" in response


def test_personality_varies_greetings_predictably() -> None:
    personality = Personality()

    first = personality.respond("greeting", "Debo", "curious")
    second = personality.respond("greeting", "Debo", "curious")
    third = personality.respond("greeting", "Debo", "curious")
    fourth = personality.respond("greeting", "Debo", "curious")

    assert first != second
    assert second != third
    assert fourth == first


def test_personality_varies_unknown_responses() -> None:
    personality = Personality()

    first = personality.respond("unknown", "Debo", "curious")
    second = personality.respond("unknown", "Debo", "curious")

    assert first != second


def test_empty_input_does_not_advance_personality() -> None:
    robot = DeskRobot()

    first = robot.respond("hello")
    robot.respond("   ")
    second = robot.respond("hello")

    comparison_robot = DeskRobot()
    comparison_robot.respond("hello")
    expected_second = comparison_robot.respond("hello")

    assert first != second
    assert second == expected_second


def test_custom_mood_is_used_in_response() -> None:
    robot = DeskRobot()
    robot.state.mood = "playful"

    response = robot.respond("how are you?")

    assert "playful" in response


def test_farewell_response_is_preserved() -> None:
    robot = DeskRobot()

    response = robot.respond("bye")

    assert "See you later!" in response


class FakeWeatherProvider:
    def fetch_current(self, location: str) -> WeatherReport:
        return WeatherReport(
            location=f"{location}, UK",
            temperature_c=14.5,
            condition="Light rain",
            provider="fake-weather",
            fetched_at=datetime.now(UTC),
            daily_high_c=16.0,
            daily_low_c=9.0,
            forecast_condition="Rain",
        )


class FakeNewsProvider:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def fetch_latest(self, limit: int = 5) -> NewsReport:
        if self.fail:
            raise InformationError("The news service is unavailable.")
        articles = (
            NewsArticle("First real headline", "Example source", "https://example.com/1"),
            NewsArticle("Second real headline", "Example source", "https://example.com/2"),
        )
        return NewsReport("Example RSS", datetime.now(UTC), articles[:limit])

    def fetch_story(self, article: NewsArticle) -> str:
        return f"Full story text for {article.title}. " + ("More reporting and detail. " * 20)


def make_information_robot(*, news_fail: bool = False) -> DeskRobot:
    return DeskRobot(
        weather_provider=FakeWeatherProvider(),
        news_provider=FakeNewsProvider(fail=news_fail),
    )


def test_weather_request_exposes_real_provider_result() -> None:
    robot = make_information_robot()
    response = robot.respond("weather in London")

    assert robot.last_intent == "weather"
    assert robot.last_weather_report is not None
    assert robot.last_weather_report.location == "London, UK"
    assert robot.last_weather_report.daily_high_c == 16.0
    assert "14.5°C" in response


def test_weather_without_location_does_not_invent_conditions() -> None:
    robot = make_information_robot()

    response = robot.respond("what is the weather?")

    assert "which location" in response.lower()
    assert robot.last_weather_report is None


def test_news_uses_a_compact_visual_first_response() -> None:
    robot = make_information_robot()

    response = robot.respond("show me the news")

    assert robot.last_news_report is not None
    assert "2 headlines" in response
    assert "First real headline" not in response


def test_next_story_advances_the_cached_news_selection() -> None:
    robot = make_information_robot()
    robot.respond("show me the news")

    response = robot.respond("next story")

    assert robot.last_intent == "next_news"
    assert robot.last_news_report is not None
    assert robot.last_news_index == 1
    assert "Second real headline" in response


def test_news_provider_failure_is_recoverable() -> None:
    robot = make_information_robot(news_fail=True)

    response = robot.respond("show me the news")

    assert "unavailable" in response.lower()
    assert robot.last_news_report is None



def test_full_story_request_reads_the_currently_selected_article() -> None:
    robot = make_information_robot()
    robot.respond("show me the news")
    robot.respond("next story")

    response = robot.respond("read the full story")

    assert robot.last_intent == "full_story"
    assert "Second real headline" in response
    assert robot.last_story_text is not None
    assert robot.last_story_text.startswith("Second real headline. Full story text for Second real headline")


def test_weather_follow_up_uses_the_clarification_context() -> None:
    robot = make_information_robot()
    question = robot.respond("give me the weather")
    assert "where should i check" in question.lower()
    assert robot.pending_intent == "weather"
    answer = robot.respond("London")
    assert robot.pending_intent is None
    assert robot.last_weather_report is not None
    assert robot.last_weather_report.location == "London, UK"
    assert "14.5°C" in answer


def test_weather_follow_up_accepts_natural_location_phrasing() -> None:
    robot = make_information_robot()
    robot.respond("what's it like outside?")
    answer = robot.respond("around Manchester")
    assert robot.last_weather_report is not None
    assert robot.last_weather_report.location == "Manchester, UK"
    assert "14.5°C" in answer


def test_weather_language_recognises_everyday_phrasing() -> None:
    robot = make_information_robot()
    response = robot.respond("Do I need an umbrella in London")
    assert robot.last_weather_report is not None
    assert robot.last_weather_report.location == "London, UK"
    assert "14.5°C" in response


def test_news_language_recognises_world_events_phrasing() -> None:
    robot = make_information_robot()
    response = robot.respond("What's going on in the world?")
    assert robot.last_news_report is not None
    assert "2 headlines" in response
