from dataclasses import dataclass


@dataclass
class RobotState:
    name: str = "Debo"
    mood: str = "curious"
    turns: int = 0


class DeskRobot:
    def __init__(self, name: str = "Debo") -> None:
        self.state = RobotState(name=name)

    def respond(self, message: str) -> str:
        message = message.strip().lower()

        if not message:
            return "I'm listening... say something!"

        self.state.turns += 1

        if message in {"hello", "hi", "hey", "hello robot"}:
            return (
                f"Hey! I'm {self.state.name}. Nice to see you! What are we doing today?"
            )

        if "your name" in message:
            return f"I'm {self.state.name}, your little desk companion."

        if "how are you" in message:
            return f"I'm feeling {self.state.mood} today. How about you?"

        if "thank" in message:
            return "You're welcome! Always happy to help."

        if message in {"bye", "goodbye", "exit", "quit"}:
            return "See you later! I'll be right here."

        if "help" in message:
            return (
                "You can say hello, ask my name, ask how I am, "
                "or just tell me something."
            )

        return (
            "Ooh, interesting! Tell me more. "
            "I'm still learning how to understand the world."
        )
