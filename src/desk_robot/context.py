from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationTurn:
    user_message: str
    assistant_response: str


class ConversationContext:
    """A small, bounded history for the current running session."""

    def __init__(self, max_turns: int = 5) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")

        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)

    @property
    def turns(self) -> tuple[ConversationTurn, ...]:
        """Return a read-only snapshot of recent conversation turns."""
        return tuple(self._turns)

    @property
    def last_user_message(self) -> str | None:
        """Return the most recent user message, if one exists."""
        if not self._turns:
            return None
        return self._turns[-1].user_message

    @property
    def last_assistant_response(self) -> str | None:
        """Return the most recent assistant response, if one exists."""
        if not self._turns:
            return None
        return self._turns[-1].assistant_response

    def add_turn(
        self,
        user_message: str,
        assistant_response: str,
    ) -> None:
        if not user_message.strip():
            raise ValueError("user_message cannot be empty")
        if not assistant_response.strip():
            raise ValueError("assistant_response cannot be empty")

        self._turns.append(
            ConversationTurn(
                user_message=user_message.strip(),
                assistant_response=assistant_response.strip(),
            )
        )

    def clear(self) -> None:
        """Forget the current session's conversation history."""
        self._turns.clear()
