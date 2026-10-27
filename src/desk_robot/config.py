"""Validated environment-backed settings for the hardware-independent brain."""
from __future__ import annotations
import os
from dataclasses import dataclass


class ConfigurationError(ValueError):
    """A configured value cannot be used safely."""

def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer.") from error
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}.")
    return value

def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a number.") from error
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return value

@dataclass(frozen=True, slots=True)
class BrainConfig:
    robot_name: str = "DEBO"
    conversation_context_turns: int = 5
    information_timeout_seconds: float = 8.0
    news_result_limit: int = 5
    laptop_bridge_enabled: bool = False

    @classmethod
    def from_environment(cls) -> BrainConfig:
        name = os.getenv("DEBO_NAME", "DEBO").strip()
        if not name or len(name) > 40:
            raise ConfigurationError("DEBO_NAME must contain 1 to 40 characters.")
        bridge = os.getenv("DEBO_LAPTOP_BRIDGE_ENABLED", "false").strip().lower()
        if bridge not in {"true", "false", "1", "0", "yes", "no"}:
            raise ConfigurationError("DEBO_LAPTOP_BRIDGE_ENABLED must be true or false.")
        return cls(
            robot_name=name,
            conversation_context_turns=_bounded_int("DEBO_CONTEXT_TURNS", 5, 1, 50),
            information_timeout_seconds=_bounded_float("DEBO_INFORMATION_TIMEOUT_SECONDS", 8.0, 0.5, 60.0),
            news_result_limit=_bounded_int("DEBO_NEWS_RESULT_LIMIT", 5, 1, 20),
            laptop_bridge_enabled=bridge in {"true", "1", "yes"},
        )
