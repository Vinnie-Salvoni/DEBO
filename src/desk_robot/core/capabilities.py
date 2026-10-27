"""Independent runtime capability tracking for DEBO."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from time import time


class Capability(StrEnum):
    """Abilities whose availability is tracked independently."""
    INTERNET = "internet"
    WEATHER = "weather"
    NEWS = "news"
    LAPTOP_BRIDGE = "laptop_bridge"
    OLLAMA = "ollama"
    MICROPHONE = "microphone"
    SPEECH_OUTPUT = "speech_output"
    FACE_DISPLAY = "face_display"

class CapabilityStatus(StrEnum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"

@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    capability: Capability
    status: CapabilityStatus
    checked_at: float | None = None
    detail: str | None = None

class CapabilityRegistry:
    """Thread-safe registry; an AI outage never implies an internet outage."""
    def __init__(self) -> None:
        self._lock = RLock()
        self._states = {item: CapabilitySnapshot(item, CapabilityStatus.UNKNOWN) for item in Capability}

    def set_status(self, capability: Capability, status: CapabilityStatus, *, detail: str | None = None, checked_at: float | None = None) -> CapabilitySnapshot:
        """Update one capability without mutating unrelated states."""
        snapshot = CapabilitySnapshot(
            capability, status, time() if checked_at is None else checked_at,
            detail.strip() or None if detail is not None else None,
        )
        with self._lock:
            self._states[capability] = snapshot
        return snapshot

    def get(self, capability: Capability) -> CapabilitySnapshot:
        with self._lock:
            return self._states[capability]

    def snapshot(self) -> tuple[CapabilitySnapshot, ...]:
        with self._lock:
            return tuple(self._states[item] for item in Capability)

    def is_available(self, capability: Capability) -> bool:
        return self.get(capability).status is CapabilityStatus.AVAILABLE
