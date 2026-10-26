from desk_robot.context import ConversationContext
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
