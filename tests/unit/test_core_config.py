import pytest

from desk_robot.config import BrainConfig, ConfigurationError


def test_config_defaults(monkeypatch) -> None:
    for key in ("DEBO_NAME", "DEBO_CONTEXT_TURNS", "DEBO_INFORMATION_TIMEOUT_SECONDS", "DEBO_NEWS_RESULT_LIMIT", "DEBO_LAPTOP_BRIDGE_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    assert BrainConfig.from_environment() == BrainConfig()


@pytest.mark.parametrize(("name", "value"), [
    ("DEBO_CONTEXT_TURNS", "0"),
    ("DEBO_CONTEXT_TURNS", "not-a-number"),
    ("DEBO_INFORMATION_TIMEOUT_SECONDS", "100"),
    ("DEBO_NEWS_RESULT_LIMIT", "0"),
    ("DEBO_LAPTOP_BRIDGE_ENABLED", "sometimes"),
    ("DEBO_NAME", "   "),
])
def test_config_rejects_invalid_values(monkeypatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError):
        BrainConfig.from_environment()

def test_config_reads_overrides(monkeypatch) -> None:
    monkeypatch.setenv("DEBO_NAME", "DEBO-Test")
    monkeypatch.setenv("DEBO_CONTEXT_TURNS", "9")
    monkeypatch.setenv("DEBO_INFORMATION_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("DEBO_NEWS_RESULT_LIMIT", "7")
    monkeypatch.setenv("DEBO_LAPTOP_BRIDGE_ENABLED", "yes")
    config = BrainConfig.from_environment()
    assert config.robot_name == "DEBO-Test"
    assert config.conversation_context_turns == 9
    assert config.information_timeout_seconds == 3.5
    assert config.news_result_limit == 7
    assert config.laptop_bridge_enabled is True
