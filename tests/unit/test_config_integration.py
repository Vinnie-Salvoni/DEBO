from desk_robot.config import BrainConfig
from desk_robot.robot import DeskRobot


class RecordingWeather:
    def __init__(self) -> None:
        self.timeout = None

    def fetch_current(self, location: str):
        raise AssertionError("Provider should not be called by this test")


class RecordingNews:
    def __init__(self) -> None:
        self.timeout = None
        self.limit = None

    def fetch_latest(self, limit: int = 5):
        self.limit = limit
        raise AssertionError("Provider should not be called by this test")


def test_robot_uses_configured_name_and_context_limit() -> None:
    config = BrainConfig(robot_name="Pip", conversation_context_turns=2)
    robot = DeskRobot(config=config)

    assert robot.state.name == "Pip"
    assert robot.context._turns.maxlen == 2


def test_explicit_constructor_arguments_override_config() -> None:
    config = BrainConfig(robot_name="Pip", conversation_context_turns=2)
    robot = DeskRobot(name="Debo", context_limit=7, config=config)

    assert robot.state.name == "Debo"
    assert robot.context._turns.maxlen == 7


def test_default_provider_timeouts_come_from_config() -> None:
    config = BrainConfig(information_timeout_seconds=3.25)
    robot = DeskRobot(config=config)

    assert robot.weather_provider.timeout == 3.25
    assert robot.news_provider.timeout == 3.25
