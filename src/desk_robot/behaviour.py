"""Small, hardware-neutral state engine for DEBO's moment-to-moment character.

This layer chooses a semantic reaction and slowly evolves bounded character
signals. It does not render graphics or decide how a physical robot should move.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BehaviourSnapshot:
    """Immutable view of the character state after an interaction."""

    reaction: str
    curiosity: float
    energy: float
    familiarity: float
    interactions: int


class BehaviourEngine:
    """Track lightweight character state and select intent-aware reactions."""

    def __init__(self) -> None:
        self.curiosity = 0.55
        self.energy = 0.72
        self.familiarity = 0.10
        self.interactions = 0
        self.last_reaction = "curious"
        self._repeated_reaction_count = 0

    @staticmethod
    def _bound(value: float) -> float:
        return max(0.0, min(1.0, value))

    def observe(self, intent: str) -> BehaviourSnapshot:
        """Update character signals and return a reaction for the current intent."""
        self.interactions += 1
        self.familiarity = self._bound(self.familiarity + 0.015)

        changes = {
            "greeting": ("greeting", 0.02, 0.04),
            "name": ("pleased", 0.01, 0.01),
            "mood": ("curious", 0.03, 0.01),
            "thanks": ("pleased", 0.01, 0.02),
            "farewell": ("sleepy", -0.01, -0.08),
            "weather": ("focused", 0.02, -0.01),
            "news": ("focused", 0.04, -0.01),
            "next_news": ("focused", 0.03, -0.02),
            "full_story": ("focused", 0.02, -0.03),
            "cancel": ("neutral", -0.02, -0.02),
            "help": ("curious", 0.01, 0.0),
            "recall": ("curious", 0.02, 0.0),
            "unknown": ("curious", 0.05, -0.01),
        }
        reaction, curiosity_delta, energy_delta = changes.get(
            intent, ("curious", 0.02, -0.01)
        )
        self.curiosity = self._bound(self.curiosity + curiosity_delta)
        self.energy = self._bound(self.energy + energy_delta)

        # Repetition is tracked rather than allowing every input to force the
        # same strong expression; the renderer can use this for subtle variation.
        if reaction == self.last_reaction:
            self._repeated_reaction_count += 1
            if self._repeated_reaction_count >= 3 and reaction == "curious":
                reaction = "focused"
                self._repeated_reaction_count = 0
        else:
            self._repeated_reaction_count = 0
        self.last_reaction = reaction
        return BehaviourSnapshot(
            reaction=reaction,
            curiosity=self.curiosity,
            energy=self.energy,
            familiarity=self.familiarity,
            interactions=self.interactions,
        )
