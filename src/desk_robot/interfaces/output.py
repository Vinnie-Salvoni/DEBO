"""Output contracts independent of Tkinter and specific audio libraries."""
from __future__ import annotations
from typing import Protocol


class FaceOutput(Protocol):
    def set_state(self, state: str) -> None:
        """Present a semantic state such as listening, thinking, or happy."""

    def close(self) -> None:
        """Release display resources."""


class SpeechOutput(Protocol):
    def speak(self, text: str) -> None:
        """Speak text, or return promptly when speech is disabled."""

    def close(self) -> None:
        """Stop playback and release resources."""


class SoundOutput(Protocol):
    def play(self, event: str) -> None:
        """Play a known sound effect if enabled."""
    def close(self) -> None:
        """Stop playback and release resources."""
