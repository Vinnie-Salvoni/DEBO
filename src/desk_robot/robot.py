from dataclasses import dataclass

from desk_robot.context import ConversationContext
from desk_robot.personality import Personality


@dataclass
class RobotState:
    name: str = "Debo"
    mood: str = "curious"
    turns: int = 0


class DeskRobot:
    def __init__(
        self,
        name: str = "Debo",
        context_limit: int = 5,
    ) -> None:
        self.state = RobotState(name=name)
        self.personality = Personality()
        self.context = ConversationContext(max_turns=context_limit)

    def respond(self, message: str) -> str:
        original_message = message.strip()
        normalised = original_message.lower()

        if not original_message:
            return "I'm listening... say something!"

        self.state.turns += 1

        # Capture the previous message before recording this question.
        previous_message = self.context.last_user_message

        if normalised in {"hello", "hi", "hey", "hello robot"}:
            intent = "greeting"
        elif "your name" in normalised or "what is your name" in normalised:
            intent = "name"
        elif "how are you" in normalised:
            intent = "mood"
        elif "thank" in normalised:
            intent = "thanks"
        elif normalised in {"bye", "goodbye", "exit", "quit"}:
            intent = "farewell"
        elif (
            "what did i just say" in normalised
            or "what did i say" in normalised
            or "what was my last message" in normalised
        ):
            intent = "recall"
        elif "help" in normalised:
            intent = "help"
        else:
            intent = "unknown"

        response = self.personality.respond(
            intent=intent,
            name=self.state.name,
            mood=self.state.mood,
            previous_message=previous_message,
        )

        self.context.add_turn(original_message, response)
        return response
