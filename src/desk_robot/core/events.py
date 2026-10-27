"""Semantic events shared by the brain and output adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import time
from typing import Any


class RobotEventType(StrEnum):
    STARTED = "started"
    USER_INPUT_RECEIVED = "user_input_received"
    BEHAVIOUR_CHANGED = "behaviour_changed"
    LISTENING_STARTED = "listening_started"
    THINKING_STARTED = "thinking_started"
    WEATHER_LOOKUP_STARTED = "weather_lookup_started"
    WEATHER_LOOKUP_SUCCEEDED = "weather_lookup_succeeded"
    WEATHER_LOOKUP_FAILED = "weather_lookup_failed"
    NEWS_LOOKUP_STARTED = "news_lookup_started"
    NEWS_RESULTS_READY = "news_results_ready"
    NEWS_LOOKUP_FAILED = "news_lookup_failed"
    SPEECH_STARTED = "speech_started"
    SPEECH_INTERRUPTED = "speech_interrupted"
    CAPABILITY_CHANGED = "capability_changed"
    TASK_SUCCEEDED = "task_succeeded"
    TASK_FAILED = "task_failed"

@dataclass(frozen=True, slots=True)
class RobotEvent:
    """A hardware-neutral event; metadata should be bounded and non-secret."""
    type: RobotEventType
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    occurred_at: float = field(default_factory=time)

    def __post_init__(self) -> None:
        if not isinstance(self.type, RobotEventType):
            raise TypeError("type must be a RobotEventType")
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")
        if not isinstance(self.data, dict):
            raise TypeError("data must be a dictionary")
        if self.occurred_at < 0:
            raise ValueError("occurred_at cannot be negative")
