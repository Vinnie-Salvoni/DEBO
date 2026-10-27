"""Input contracts independent of the chosen UI or microphone."""
from __future__ import annotations
from collections.abc import Callable
from typing import Protocol

InputHandler = Callable[[str], None]

class InputSource(Protocol):
    def start(self, on_input: InputHandler) -> None:
        """Begin receiving input and deliver each command to the callback."""
    def close(self) -> None:
        """Release resources and stop background activity."""
