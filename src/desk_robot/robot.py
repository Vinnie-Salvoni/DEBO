import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from desk_robot.behaviour import BehaviourEngine
from desk_robot.config import BrainConfig
from desk_robot.context import ConversationContext
from desk_robot.core.capabilities import Capability, CapabilityRegistry, CapabilityStatus
from desk_robot.core.events import RobotEvent, RobotEventType
from desk_robot.information import (
    InformationError,
    NewsProvider,
    OpenMeteoWeatherProvider,
    RssNewsProvider,
    WeatherProvider,
)
from desk_robot.personality import Personality

logger = logging.getLogger(__name__)


@dataclass
class RobotState:
    name: str = "Debo"
    mood: str = "curious"
    turns: int = 0


class DeskRobot:
    def __init__(
        self,
        name: str | None = None,
        context_limit: int | None = None,
        weather_provider: WeatherProvider | None = None,
        news_provider: NewsProvider | None = None,
        config: BrainConfig | None = None,
        event_sink: Callable[[RobotEvent], None] | None = None,
    ) -> None:
        self.config = config if config is not None else BrainConfig.from_environment()
        resolved_name = name if name is not None else self.config.robot_name
        resolved_context_limit = (
            context_limit
            if context_limit is not None
            else self.config.conversation_context_turns
        )
        self.state = RobotState(name=resolved_name)
        self.capabilities = CapabilityRegistry()
        self._event_sink = event_sink
        self.personality = Personality()
        self.behaviour = BehaviourEngine()
        self.context = ConversationContext(max_turns=resolved_context_limit)
        self.weather_provider = (
            weather_provider
            if weather_provider is not None
            else OpenMeteoWeatherProvider(timeout=self.config.information_timeout_seconds)
        )
        self.news_provider = (
            news_provider
            if news_provider is not None
            else RssNewsProvider(timeout=self.config.information_timeout_seconds)
        )
        self.last_weather_report = None
        self.last_news_report = None
        self.last_intent = "unknown"
        self.news_cache = None
        self.last_news_index = 0
        self.last_story_text: str | None = None
        self.pending_intent: str | None = None
        self.last_weather_location: str | None = None

    def _emit_event(
        self,
        event_type: RobotEventType,
        *,
        message: str = "",
        data: dict[str, object] | None = None,
    ) -> None:
        """Notify optional observers without letting a renderer break the brain."""
        if self._event_sink is None:
            return
        try:
            self._event_sink(
                RobotEvent(type=event_type, message=message, data={} if data is None else data)
            )
        except Exception:
            logger.exception("DEBO event sink failed for %s", event_type.value)

    def _set_capability_status(
        self,
        capability: Capability,
        status: CapabilityStatus,
        *,
        detail: str | None = None,
    ) -> None:
        snapshot = self.capabilities.set_status(capability, status, detail=detail)
        self._emit_event(
            RobotEventType.CAPABILITY_CHANGED,
            message=detail or "",
            data={"capability": capability.value, "status": snapshot.status.value},
        )

    def respond(self, message: str) -> str:
        original_message = message.strip()
        normalised = original_message.lower()

        if not original_message:
            return "I'm listening... say something!"

        self._emit_event(
            RobotEventType.USER_INPUT_RECEIVED, data={"character_count": len(original_message)}
        )
        self.state.turns += 1
        previous_message = self.context.last_user_message
        self.last_weather_report = None
        self.last_news_report = None
        self.last_intent = "unknown"
        self.last_story_text = None

        intent = "unknown"

        if normalised in {
            "forget our conversation",
            "forget this conversation",
            "forget what i've told you",
            "forget what i have told you",
            "clear our conversation",
            "clear conversation history",
            "clear our chat history",
        }:
            intent = "forget_context"
        elif normalised in {"cancel", "cancel that", "never mind", "nevermind", "forget it", "stop", "don't worry", "dont worry"}:
            intent = "cancel"
        elif normalised in {"hello", "hi", "hey", "hello robot"}:
            intent = "greeting"
        elif any(phrase in normalised for phrase in (
            "tell me about yourself",
            "what are you like",
            "describe yourself",
            "what do you like",
            "what kind of robot are you",
        )):
            intent = "about"
        elif "your name" in normalised or "what is your name" in normalised:
            intent = "name"
        elif "how are you" in normalised:
            intent = "mood"
        elif "thank" in normalised:
            intent = "thanks"
        elif normalised in {"bye", "goodbye", "exit", "quit"}:
            intent = "farewell"
        elif any(phrase in normalised for phrase in (
            "what did you just say",
            "what were you saying",
            "what was your last answer",
            "repeat your last answer",
            "can you repeat that",
            "say that again",
        )):
            intent = "recall_response"
        elif (
            "what did i just say" in normalised
            or "what did i say" in normalised
            or "what was my last message" in normalised
        ):
            intent = "recall"
        elif "help" in normalised:
            intent = "help"
        elif self._is_weather_request(normalised) or (
            self.last_weather_location
            and re.match(r"^(?:and\s+)?what about\s+.+[?.!]*$", normalised)
        ):
            intent = "weather"
        elif any(phrase in normalised for phrase in ("read the full story", "read full story", "read me the story", "read this story", "full story", "read the article", "read article")):
            intent = "full_story"
        elif any(phrase in normalised for phrase in ("next story", "another story", "next headline")):
            intent = "next_news"
        elif self.news_cache and any(
            phrase in normalised
            for phrase in (
                "tell me more",
                "more details",
                "expand on that",
                "tell me more about that",
                "what happened next",
            )
        ):
            intent = "full_story"
        elif self._is_news_request(normalised):
            intent = "news"

        if intent == "unknown" and self.pending_intent == "weather":
            if self._clean_follow_up_location(original_message):
                intent = "weather"
            else:
                self.pending_intent = None
        elif self.pending_intent == "weather" and intent != "weather":
            self.pending_intent = None

        # A location comparison only makes sense as an immediate weather follow-up.
        # Don't let an old weather topic hijack a later, unrelated conversation.
        if intent != "weather":
            self.last_weather_location = None

        # News follow-ups belong to the active news exchange, not indefinitely
        # to the most recent headlines fetched in an earlier topic.
        if intent not in {"news", "next_news", "full_story"}:
            self.news_cache = None
            self.last_news_index = 0
            self.last_story_text = None

        self.last_intent = intent
        reaction = self.behaviour.observe(intent)
        self._emit_event(
            RobotEventType.BEHAVIOUR_CHANGED,
            data={
                "intent": intent,
                "reaction": reaction.reaction,
                "curiosity": reaction.curiosity,
                "energy": reaction.energy,
                "familiarity": reaction.familiarity,
                "interactions": reaction.interactions,
            },
        )

        if intent == "forget_context":
            self.context.clear()
            self.pending_intent = None
            self.news_cache = None
            self.last_news_index = 0
            self.last_story_text = None
            self.last_weather_location = None
            response = "All right — I've cleared our conversation history and my saved news selection for this session."
        elif intent == "cancel":
            self.pending_intent = None
            response = "No problem — cancelled. What would you like to do instead?"
        elif intent == "weather":
            location = self._weather_location(original_message)
            if not location and re.match(r"^(?:and\s+)?what about\s+", normalised):
                location = re.sub(
                    r"^(?:and\s+)?what about\s+", "", original_message, flags=re.IGNORECASE
                ).strip(" .?!")
            if not location and self.pending_intent == "weather":
                location = self._clean_follow_up_location(original_message)

            if not location:
                self.pending_intent = "weather"
                response = "Which location should I check? Tell me a city or town, and I'll get the weather."
            else:
                self.pending_intent = None
                self._emit_event(
                    RobotEventType.WEATHER_LOOKUP_STARTED, message="Retrieving current weather."
                )
                try:
                    report = self.weather_provider.fetch_current(location)
                    self.last_weather_report = report
                    self.last_weather_location = location
                    self._set_capability_status(Capability.WEATHER, CapabilityStatus.AVAILABLE)
                    self._emit_event(
                        RobotEventType.WEATHER_LOOKUP_SUCCEEDED,
                        data={"location": report.location, "provider": report.provider},
                    )
                    response = (
                        f"Here's the current weather for {report.location}: "
                        f"{report.condition}, {report.temperature_c:.1f}°C. "
                        f"Source: {report.provider}."
                    )
                    if report.observed_at is not None:
                        response += (
                            " Conditions observed at "
                            f"{report.observed_at.strftime('%H:%M UTC')}."
                        )
                except InformationError as error:
                    self._set_capability_status(
                        Capability.WEATHER, CapabilityStatus.UNAVAILABLE, detail=str(error)
                    )
                    self._emit_event(RobotEventType.WEATHER_LOOKUP_FAILED, message=str(error))
                    response = str(error)

        elif intent == "recall_response":
            previous_response = self.context.last_assistant_response
            if previous_response is None:
                response = "I haven't given you an earlier answer in this session yet."
            else:
                response = f'I said: "{previous_response}"'

        elif intent == "news":
            self._emit_event(RobotEventType.NEWS_LOOKUP_STARTED, message="Retrieving headlines.")
            try:
                report = self.news_provider.fetch_latest(limit=self.config.news_result_limit)
                self.last_news_report = report
                self._set_capability_status(
                    Capability.NEWS,
                    CapabilityStatus.AVAILABLE if report.articles else CapabilityStatus.UNAVAILABLE,
                    detail=None if report.articles else "The news feed returned no headlines.",
                )
                self._emit_event(
                    RobotEventType.NEWS_RESULTS_READY if report.articles else RobotEventType.NEWS_LOOKUP_FAILED,
                    message="" if report.articles else "The news feed returned no headlines.",
                    data={"article_count": len(report.articles), "provider": report.provider},
                )
                self.news_cache = report
                self.last_news_index = 0
                if report.articles:
                    response = f"I've found {len(report.articles)} headlines. Want the next story?"
                else:
                    response = "The news feed returned no headlines."
            except InformationError as error:
                self._set_capability_status(
                    Capability.NEWS, CapabilityStatus.UNAVAILABLE, detail=str(error)
                )
                self._emit_event(RobotEventType.NEWS_LOOKUP_FAILED, message=str(error))
                response = str(error)

        elif intent == "full_story":
            if not self.news_cache or not self.news_cache.articles:
                response = "Ask me for the news first, then say read the full story."
            else:
                index = min(max(0, self.last_news_index), len(self.news_cache.articles) - 1)
                article = self.news_cache.articles[index]
                self.last_news_report = self.news_cache
                fetch_story = getattr(self.news_provider, "fetch_story", None)
                if fetch_story is None:
                    response = "This news source doesn't support full-story reading yet."
                else:
                    try:
                        self.last_story_text = f"{article.title}. {fetch_story(article)}"
                        response = f"All right. I'll read the full story: {article.title}."
                    except InformationError as error:
                        response = str(error)
                        self.last_story_text = None

        elif intent == "next_news":
            if self.news_cache and self.news_cache.articles:
                self.last_news_report = self.news_cache
                self.last_news_index = (self.last_news_index + 1) % len(self.news_cache.articles)
                article = self.news_cache.articles[self.last_news_index]
                response = f"Story {self.last_news_index + 1} of {len(self.news_cache.articles)}: {article.title}"
            else:
                response = "Ask me for the news first, and I'll find a story for you."

        else:
            response = self.personality.respond(
                intent=intent,
                name=self.state.name,
                mood=self.state.mood,
                previous_message=previous_message,
            )

        if intent != "forget_context":
            self.context.add_turn(original_message, response)
        return response

    @staticmethod
    def _is_weather_request(message: str) -> bool:
        text = message.lower().strip()
        return bool(
            re.search(r"\b(weather|temperature|forecast|rain|raining|sunny|windy)\b", text)
            or any(phrase in text for phrase in (
                "will it rain", "is it cold", "is it hot", "what's it like outside",
                "what is it like outside", "do i need an umbrella",
            ))
        )

    @staticmethod
    def _is_news_request(message: str) -> bool:
        text = message.lower().strip()
        return bool(
            re.search(r"\b(news|headlines|current events)\b", text)
            or any(phrase in text for phrase in (
                "latest stories", "what's happening", "what is happening",
                "what's going on in the world", "anything happening today",
                "tell me what's going on",
            ))
        )

    def cancel_pending_intent(self) -> None:
        """Clear an unfinished clarification when its voice window expires."""
        self.pending_intent = None

    @staticmethod
    def _clean_follow_up_location(message: str) -> str | None:
        location = message.strip(" .,!?:;")
        location = re.sub(
            r"^(?:it's|it is|in|for|around|near|the weather in|check|try|use)\s+",
            "", location, flags=re.IGNORECASE,
        )
        lowered = location.lower()
        if (
            not location
            or lowered in {"there", "here", "that place", "anywhere"}
            or len(location.split()) > 6
            or re.search(
                r"\b(i|i'm|i am|you|we|they|he|she|it|what|why|how|can|could|would|please|tell|show|help|cancel|stop|thanks|thank)\b",
                lowered,
            )
        ):
            return None
        return location

    @staticmethod
    def _weather_location(message: str) -> str | None:
        normalised = message.lower()
        markers = (
            "weather in ",
            "weather for ",
            "temperature in ",
            "temperature for ",
            "forecast in ",
            "forecast for ",
            "umbrella in ",
        )

        for marker in markers:
            position = normalised.find(marker)
            if position >= 0:
                location = message[position + len(marker) :].strip(" .?!")
                return location or None

        return None
