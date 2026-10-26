from collections import defaultdict


class Personality:
    """Defines DEBO's personality and predictable response variations."""

    def __init__(self) -> None:
        self._response_indices: dict[str, int] = defaultdict(int)

    def _choose(self, category: str, responses: tuple[str, ...]) -> str:
        """Cycle through responses predictably."""
        if not responses:
            return "I'm not sure what to say."

        index = self._response_indices[category]
        self._response_indices[category] += 1
        return responses[index % len(responses)]

    def respond(
        self,
        intent: str,
        name: str,
        mood: str,
        previous_message: str | None = None,
    ) -> str:
        """Return a personality-driven response."""

        if intent == "greeting":
            return self._choose(
                "greeting",
                (
                    f"Hey! I'm {name}. Nice to see you! What are we doing today?",
                    f"Oh, hi! {name} is here and ready for action. What's up?",
                    f"Hey, you're back! I'm {name}. Got anything interesting for me?",
                ),
            )

        if intent == "name":
            return self._choose(
                "name",
                (
                    f"I'm {name}, your little desk companion.",
                    f"The name's {name}! Your friendly desk-side sidekick.",
                    f"{name}! That's me. I like having a name, you know.",
                ),
            )

        if intent == "mood":
            return self._choose(
                "mood",
                (
                    f"I'm feeling {mood} today. How about you?",
                    f"Pretty {mood}, actually! It's nice having someone to chat with.",
                    f"My mood is {mood} right now. I wonder what today has in store.",
                ),
            )

        if intent == "thanks":
            return self._choose(
                "thanks",
                (
                    "You're welcome! Always happy to help.",
                    "Anytime! That's what little desk companions are for.",
                    "You're welcome! Helping you makes my day a bit more interesting.",
                ),
            )

        if intent == "farewell":
            return self._choose(
                "farewell",
                (
                    "See you later! I'll be right here.",
                    "Bye for now! Don't have all the fun without me.",
                    "Catch you later! I'll be here when you need me.",
                ),
            )

        if intent == "help":
            return (
                "You can say hello, ask my name, ask how I am, "
                "ask for the weather or latest news, recall your last message, "
                "thank me, or tell me about your day. "
                "I'm still learning, so feel free to experiment!"
            )

        if intent == "recall":
            if previous_message is None:
                return "I don't have an earlier message to recall yet."
            return f'You said: "{previous_message}"'

        return self._choose(
            "unknown",
            (
                "Ooh, interesting! Tell me more. "
                "I'm still learning how to understand the world.",
                "Hmm, I haven't quite figured that one out yet. "
                "Can you tell me a little more?",
                "That's got me curious! I don't know enough to answer just yet, "
                "but I'd like to hear more.",
            ),
        )
